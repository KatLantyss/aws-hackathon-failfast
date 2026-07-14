.PHONY: dev dev-api dev-frontend stop stop-all build prod prod-backend prod-frontend predict clean

# AWS profile for hackathon credentials
AWS_PROFILE  ?= hackathon
AWS_REGION   ?= us-east-1
ACCOUNT_ID   ?= 151274905459
API_PORT     ?= 8000
DOCKER_IMAGE  = ship-analysis-api:local

# ECR repos
ECR_BACKEND  = $(ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/ship-analysis-api
ECR_FRONTEND = $(ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/ym-fleet-ops-frontend

# ECS
ECS_CLUSTER       = ship-analysis
ECS_BACKEND_SVC   = ship-api-svc
ECS_BACKEND_TDEF  = ship-api
ECS_FRONTEND_SVC  = ym-fleet-ops-frontend-svc

# Production URLs
BACKEND_CF_URL  = https://d1yvzz0da29zvi.cloudfront.net
FRONTEND_CF_URL = https://d1yvzz0da29zvi.cloudfront.net

# ── Dev（同時啟動 backend + frontend）─────────────────────────────────────────
# 使用方式：make dev
dev:
	@$(MAKE) dev-api > /dev/null 2>&1
	@cd frontend && VITE_BACKEND_BASE_URL=http://localhost:$(API_PORT) npm run dev > /tmp/vite.log 2>&1 &
	@sleep 2
	@echo ""
	@printf "┌──────────────────────────────────────────────┐\n"
	@printf "│   Ship Analysis -- Dev Environment           │\n"
	@printf "│                                              │\n"
	@printf "│   Backend API  ->  http://localhost:8000     │\n"
	@printf "│   Frontend     ->  http://localhost:5173     │\n"
	@printf "│                                              │\n"
	@printf "│   make stop-all  to stop everything          │\n"
	@printf "└──────────────────────────────────────────────┘\n"
	@echo ""

# ── Backend only（直接跑 uvicorn，不用 Docker）────────────────────────────────
dev-api:
	@docker rm -f ship-api-local 2>/dev/null || true
	@pkill -f "uvicorn app:app" 2>/dev/null || true
	@sleep 1
	@cd backend-api && \
		AWS_REGION=us-east-1 \
		AWS_DEFAULT_REGION=us-east-1 \
		AWS_ACCESS_KEY_ID=$$(aws configure get aws_access_key_id --profile $(AWS_PROFILE)) \
		AWS_SECRET_ACCESS_KEY=$$(aws configure get aws_secret_access_key --profile $(AWS_PROFILE)) \
		AWS_SESSION_TOKEN=$$(aws configure get aws_session_token --profile $(AWS_PROFILE)) \
		VESSEL_TABLE=ship-analysis-dev-vessel-data \
		MAINT_TABLE=ship-analysis-dev-maintenance-events \
		FLEET_SUMMARY_TABLE=ship-analysis-dev-fleet-summary \
		uvicorn app:app --host 0.0.0.0 --port $(API_PORT) > /tmp/backend-api.log 2>&1 &
	@sleep 2
	@echo "✅  Backend running at http://localhost:$(API_PORT)"
	@echo "    Health: $$(curl -s http://localhost:$(API_PORT)/health)"

# ── Frontend only ─────────────────────────────────────────────────────────────
dev-frontend:
	@cd frontend && \
		VITE_BACKEND_BASE_URL=http://localhost:$(API_PORT) \
		npm run dev

# ── Stop all ────────────────────────────────────────────────────────────────
stop-all: stop
	@pkill -f "vite" 2>/dev/null && echo "✅  Frontend stopped" || echo "No frontend running"

# ── Stop backend ─────────────────────────────────────────────────────────────
stop:
	@pkill -f "uvicorn app:app" 2>/dev/null && echo "✅  Backend stopped" || echo "No backend running"

# ── Build Docker image（本機 arm64 測試用）────────────────────────────────────
build:
	@cd backend-api && docker build -t $(DOCKER_IMAGE) .
	@echo "✅  Built $(DOCKER_IMAGE)"

# ════════════════════════════════════════════════════════════════════════════
# PRODUCTION DEPLOY  (make prod)
# Builds both images for linux/amd64, pushes to ECR, updates ECS services.
# Prerequisites:
#   - Docker running
#   - AWS profile "hackathon" authenticated  (run: make prod-login)
#   - ANTHROPIC_API_KEY and OPENAI_API_KEY set in environment (for frontend)
# ════════════════════════════════════════════════════════════════════════════

# ── ECR login ─────────────────────────────────────────────────────────────────
prod-login:
	@aws ecr get-login-password --region $(AWS_REGION) --profile $(AWS_PROFILE) \
		| docker login --username AWS --password-stdin $(ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
	@echo "✅  Logged in to ECR"

# ── Full production deploy (backend + frontend) ───────────────────────────────
prod: prod-login prod-backend prod-frontend
	@echo ""
	@printf "┌──────────────────────────────────────────────────────────────┐\n"
	@printf "│   Production Deploy Complete                                  │\n"
	@printf "│                                                              │\n"
	@printf "│   Backend API  ->  $(BACKEND_CF_URL)   │\n"
	@printf "│   Frontend     ->  $(FRONTEND_CF_URL)   │\n"
	@printf "│                                                              │\n"
	@printf "│   ECS may take 1-3 min to roll out new tasks                 │\n"
	@printf "└──────────────────────────────────────────────────────────────┘\n"

# ── Deploy backend ────────────────────────────────────────────────────────────
# 1. Build for linux/amd64 (required for ECS EC2 X86_64)
# 2. Push to ECR
# 3. Register new task definition revision (adds FLEET_SUMMARY_TABLE)
# 4. Force new deployment on ECS service
prod-backend: prod-login
	@echo "▶  Building backend image (linux/amd64)..."
	@cd backend-api && docker build --platform linux/amd64 -t $(ECR_BACKEND):latest .
	@echo "▶  Pushing backend to ECR..."
	@docker push $(ECR_BACKEND):latest
	@echo "▶  Registering new ECS task definition..."
	@aws ecs register-task-definition \
		--profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--family $(ECS_BACKEND_TDEF) \
		--task-role-arn arn:aws:iam::$(ACCOUNT_ID):role/ecsTaskRole-ship \
		--execution-role-arn arn:aws:iam::$(ACCOUNT_ID):role/ecsTaskExecRole-ship \
		--network-mode host \
		--container-definitions '[{
			"name": "ship-api",
			"image": "$(ECR_BACKEND):latest",
			"cpu": 512,
			"memory": 1024,
			"portMappings": [{"containerPort": 8000, "hostPort": 8000, "protocol": "tcp"}],
			"essential": true,
			"environment": [
				{"name": "AWS_REGION",           "value": "$(AWS_REGION)"},
				{"name": "VESSEL_TABLE",          "value": "ship-analysis-dev-vessel-data"},
				{"name": "MAINT_TABLE",           "value": "ship-analysis-dev-maintenance-events"},
				{"name": "FLEET_SUMMARY_TABLE",   "value": "ship-analysis-dev-fleet-summary"}
			],
			"logConfiguration": {
				"logDriver": "awslogs",
				"options": {
					"awslogs-group": "/ecs/ship-api",
					"awslogs-create-group": "true",
					"awslogs-region": "$(AWS_REGION)",
					"awslogs-stream-prefix": "ecs"
				}
			}
		}]' \
		--query 'taskDefinition.taskDefinitionArn' --output text
	@echo "▶  Deploying backend to ECS..."
	@aws ecs update-service \
		--profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--cluster $(ECS_CLUSTER) \
		--service $(ECS_BACKEND_SVC) \
		--task-definition $(ECS_BACKEND_TDEF) \
		--force-new-deployment \
		--query 'service.deployments[0].{status:status,desired:desiredCount}' \
		--output table
	@echo "✅  Backend deploy triggered → $(BACKEND_CF_URL)/health"

# ── Deploy frontend ───────────────────────────────────────────────────────────
# 1. npm run build (Vite) with prod backend URL injected
# 2. Build Docker image for linux/amd64
# 3. Create ECR repo if missing, push image
# 4. Create or update ECS Express Mode service
prod-frontend: prod-login
	@echo "▶  Building frontend (npm run build)..."
	@cd frontend && VITE_BACKEND_BASE_URL=$(BACKEND_CF_URL) npm run build
	@echo "▶  Building frontend Docker image (linux/amd64)..."
	@cd frontend && docker build --platform linux/amd64 -t $(ECR_FRONTEND):latest .
	@echo "▶  Creating ECR repo if needed..."
	@aws ecr describe-repositories --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--repository-names ym-fleet-ops-frontend 2>/dev/null \
		|| aws ecr create-repository --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		   --repository-name ym-fleet-ops-frontend
	@echo "▶  Pushing frontend to ECR..."
	@docker push $(ECR_FRONTEND):latest
	@echo "▶  Creating or updating ECS Express Mode service..."
	@aws ecs describe-express-gateway-service \
		--profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--service-name $(ECS_FRONTEND_SVC) 2>/dev/null \
	&& aws ecs update-express-gateway-service \
		--profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--service-name $(ECS_FRONTEND_SVC) \
		--primary-container "{\"image\":\"$(ECR_FRONTEND):latest\"}" \
		--monitor-resources \
	|| aws ecs create-express-gateway-service \
		--profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--service-name $(ECS_FRONTEND_SVC) \
		--execution-role-arn arn:aws:iam::$(ACCOUNT_ID):role/ecsTaskExecutionRole \
		--infrastructure-role-arn arn:aws:iam::$(ACCOUNT_ID):role/ecsInfrastructureRoleForExpressServices \
		--health-check-path "/health" \
		--primary-container "{
			\"image\": \"$(ECR_FRONTEND):latest\",
			\"containerPort\": 8080,
			\"environment\": [
				{\"name\": \"ANTHROPIC_MODEL\", \"value\": \"claude-sonnet-5\"},
				{\"name\": \"OPENAI_STT_MODEL\", \"value\": \"gpt-4o-transcribe\"}
			]
		}" \
		--monitor-resources
	@echo "✅  Frontend deploy complete"

# ── (Optional) Update CloudFront to route frontend + backend on one domain ───
# Run AFTER prod-frontend completes and you have the ECS Express Mode URL.
# Set FRONTEND_ECS_URL to the Express Mode endpoint before running.
# e.g.:  make prod-cloudfront FRONTEND_ECS_URL=https://ym-fleet-ops-frontend-svc.ecs.us-east-1.on.aws
FRONTEND_ECS_URL ?= https://REPLACE-WITH-ECS-EXPRESS-URL.ecs.us-east-1.on.aws
prod-cloudfront:
	@test "$(FRONTEND_ECS_URL)" != "https://REPLACE-WITH-ECS-EXPRESS-URL.ecs.us-east-1.on.aws" \
		|| (echo "❌  Set FRONTEND_ECS_URL first.  e.g.: make prod-cloudfront FRONTEND_ECS_URL=https://..." && exit 1)
	@echo "▶  Fetching current CloudFront config..."
	@CF_ETAG=$$(aws cloudfront get-distribution-config --profile $(AWS_PROFILE) \
		--id EYQC35Y9OSEQD --query 'ETag' --output text) && \
	aws cloudfront get-distribution-config --profile $(AWS_PROFILE) \
		--id EYQC35Y9OSEQD --query 'DistributionConfig' > /tmp/cf-config.json && \
	echo "Got ETag: $$CF_ETAG" && \
	python3 scripts/patch_cloudfront.py /tmp/cf-config.json "$(FRONTEND_ECS_URL)" > /tmp/cf-config-patched.json && \
	aws cloudfront update-distribution --profile $(AWS_PROFILE) \
		--id EYQC35Y9OSEQD \
		--if-match "$$CF_ETAG" \
		--distribution-config file:///tmp/cf-config-patched.json \
		--query 'Distribution.Status' --output text && \
	echo "✅  CloudFront update submitted (status: InProgress → ~5 min to Deployed)"

# ── 批次預測 → submission.csv ─────────────────────────────────────────────────
# 預設打 CloudFront；若要打本機：make predict URL=http://localhost:8000
URL ?= https://d1yvzz0da29zvi.cloudfront.net
predict:
	@python3 backend-api/predict_submit.py --url $(URL) --verbose

# ── 清除 ─────────────────────────────────────────────────────────────────────
clean:
	@docker rm -f ship-api-local 2>/dev/null || true
	@find . -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	@find . -name '*.pyc' -delete 2>/dev/null || true
	@echo "✅  Cleaned"
