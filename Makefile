.PHONY: dev dev-api dev-frontend stop stop-all build prod prod-login prod-backend prod-frontend predict clean

# AWS profile for hackathon credentials
AWS_PROFILE  ?= hackathon
AWS_REGION   ?= us-east-1
ACCOUNT_ID   ?= 151274905459
API_PORT     ?= 8000
DOCKER_IMAGE  = ship-analysis-api:local

# ECR repos
ECR_BACKEND  = $(ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/ship-analysis-api

# ECS
ECS_CLUSTER       = ship-analysis
ECS_BACKEND_SVC   = ship-api-svc
ECS_BACKEND_TDEF  = ship-api

# Production URL (CloudFront — serves both frontend S3 and backend /api/*)
BACKEND_CF_URL  = https://d1yvzz0da29zvi.cloudfront.net

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
# frontend is deployed to S3 + CloudFront (static SPA, no container needed)
prod: prod-login prod-backend prod-frontend
	@echo ""
	@printf "┌──────────────────────────────────────────────────────────────┐\n"
	@printf "│   Production Deploy Complete                                 │\n"
	@printf "│                                                              │\n"
	@printf "│   App  ->  https://d1yvzz0da29zvi.cloudfront.net            │\n"
	@printf "│   API  ->  https://d1yvzz0da29zvi.cloudfront.net/api/v1/    │\n"
	@printf "│                                                              │\n"
	@printf "│   CloudFront takes ~5 min to fully propagate                 │\n"
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
	@echo "▶  Generating task definition JSON..."
	@python3 scripts/gen_taskdef.py $(ECR_BACKEND):latest $(AWS_REGION) $(ACCOUNT_ID) /tmp/ship-api-taskdef.json
	@echo "▶  Registering new ECS task definition..."
	@NEW_ARN=$$(aws ecs register-task-definition \
		--profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--cli-input-json file:///tmp/ship-api-taskdef.json \
		--query 'taskDefinition.taskDefinitionArn' --output text) && \
		echo "  Registered: $$NEW_ARN"
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
# ── Deploy frontend to S3 + CloudFront (static SPA) ──────────────────────────
# 1. npm run build → dist/
# 2. setup_s3_frontend.py: create bucket, OAC, update CloudFront routing
# 3. aws s3 sync dist/ → S3 bucket
# 4. CloudFront cache invalidation
prod-frontend:
	@echo "▶  Building frontend (npm run build)..."
	@cd frontend && VITE_BACKEND_BASE_URL=$(BACKEND_CF_URL) npm run build
	@echo "▶  Setting up S3 bucket + CloudFront routing..."
	@BUCKET=$$(python3 scripts/setup_s3_frontend.py \
		--profile $(AWS_PROFILE) \
		--region $(AWS_REGION) \
		--account-id $(ACCOUNT_ID) \
		--distribution-id EYQC35Y9OSEQD \
		--backend-origin-id ship-api-ec2 \
		| tee /dev/stderr | grep '^BUCKET=' | cut -d= -f2) && \
	echo "▶  Syncing dist/ to s3://$$BUCKET ..." && \
	aws s3 sync frontend/dist/ s3://$$BUCKET/ \
		--profile $(AWS_PROFILE) \
		--delete \
		--cache-control "no-cache" \
		--exclude "assets/*" && \
	aws s3 sync frontend/dist/assets/ s3://$$BUCKET/assets/ \
		--profile $(AWS_PROFILE) \
		--delete \
		--cache-control "public,max-age=31536000,immutable" && \
	echo "▶  Invalidating CloudFront cache..." && \
	aws cloudfront create-invalidation \
		--profile $(AWS_PROFILE) \
		--distribution-id EYQC35Y9OSEQD \
		--paths "/*" \
		--query 'Invalidation.{Id:Id,Status:Status}' --output table && \
	echo "✅  Frontend deployed → https://d1yvzz0da29zvi.cloudfront.net"

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
