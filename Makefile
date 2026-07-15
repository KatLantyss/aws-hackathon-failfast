.PHONY: setup check-dev check-frontend local dev dev-api dev-frontend stop stop-all build prod prod-login prod-backend prod-frontend predict clean

# Local development uses the existing Python 3.14 environment. The production
# Docker image remains Python 3.12 and is intentionally independent.
VENV         ?= .venv314
VENV_PYTHON  := $(CURDIR)/$(VENV)/bin/python
VENV_UVICORN := $(CURDIR)/$(VENV)/bin/uvicorn

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

# ── Local bootstrap and preflight ────────────────────────────────────────────
setup:
	@test -x $(VENV_PYTHON) && test -x $(VENV_UVICORN) || { echo "ERROR: Python 3.14 environment '$(VENV)' is missing or incomplete."; exit 1; }
	@$(VENV_PYTHON) -c "import fastapi, uvicorn, boto3, pandas, numpy, sklearn, xgboost"
	@npm --prefix frontend ci
	@echo "✅  Local frontend dependencies installed; Python 3.14 environment verified. Configure AWS profile '$(AWS_PROFILE)', then run make dev."

check-dev:
	@test -x $(VENV_UVICORN) || { echo "ERROR: Python 3.14 backend environment '$(VENV)' is missing. Restore it before running make local."; exit 1; }
	@$(VENV_PYTHON) -c "import fastapi, uvicorn, boto3, pandas, numpy, sklearn, xgboost" || { echo "ERROR: Python 3.14 backend dependencies are incomplete in '$(VENV)'."; exit 1; }
	@test -d frontend/node_modules || { echo "ERROR: Frontend dependencies are missing. Run 'npm --prefix frontend ci' or 'make setup'."; exit 1; }
	@aws configure list-profiles | grep -Fxq "$(AWS_PROFILE)" || { echo "ERROR: AWS profile '$(AWS_PROFILE)' is not configured. See README.md."; exit 1; }

check-frontend:
	@test -d frontend/node_modules || { echo "ERROR: Frontend dependencies are missing. Run 'npm --prefix frontend ci' or 'make setup'."; exit 1; }

# ── Local（本機 backend 直連 DynamoDB + 本機 frontend）────────────────────────
# 使用方式：make local
local: check-dev
	@pkill -f "vite" 2>/dev/null || true
	@$(MAKE) dev-api
	@cd frontend && AWS_PROFILE=$(AWS_PROFILE) AWS_SDK_LOAD_CONFIG=1 VITE_BACKEND_BASE_URL=http://localhost:$(API_PORT) npm run dev -- --port 5173 --strictPort --host 127.0.0.1 > /tmp/vite.log 2>&1 &
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
		if curl -fsS http://127.0.0.1:5173 >/dev/null; then \
			break; \
		fi; \
		sleep 2; \
	done; \
	if ! curl -fsS http://127.0.0.1:5173 >/dev/null; then \
		echo "ERROR: Frontend did not become ready within 30 seconds. /tmp/vite.log:"; \
		cat /tmp/vite.log; \
		$(MAKE) stop; \
		exit 1; \
	fi
	@echo ""
	@printf "┌──────────────────────────────────────────────────────────┐\n"
	@printf "│   Ship Analysis -- Local Environment                     │\n"
	@printf "│                                                          │\n"
	@printf "│   Frontend     ->  http://localhost:5173                │\n"
	@printf "│   Backend API  ->  http://localhost:8000 (local uvicorn) │\n"
	@printf "│   Data         ->  DynamoDB directly (hackathon profile) │\n"
	@printf "│                                                          │\n"
	@printf "│   make stop-all  to stop everything                     │\n"
	@printf "└──────────────────────────────────────────────────────────┘\n"
	@echo ""

# ── Dev（frontend 直接打正式 CloudFront，不啟動本機 backend）──────────────────
# 使用方式：make dev
dev: check-frontend
	@$(MAKE) stop 2>/dev/null || true
	@pkill -f "vite" 2>/dev/null || true
	@cd frontend && VITE_BACKEND_BASE_URL=$(BACKEND_CF_URL) npm run dev -- --port 5173 --strictPort --host 127.0.0.1 > /tmp/vite.log 2>&1 &
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
		if curl -fsS http://127.0.0.1:5173 >/dev/null; then \
			break; \
		fi; \
		sleep 2; \
	done; \
	if ! curl -fsS http://127.0.0.1:5173 >/dev/null; then \
		echo "ERROR: Frontend did not become ready within 30 seconds. /tmp/vite.log:"; \
		cat /tmp/vite.log; \
		exit 1; \
	fi
	@echo ""
	@printf "┌──────────────────────────────────────────────────────────┐\n"
	@printf "│   Ship Analysis -- Dev Environment (prod API)            │\n"
	@printf "│                                                          │\n"
	@printf "│   Frontend  ->  http://localhost:5173                   │\n"
	@printf "│   Backend   ->  $(BACKEND_CF_URL)  │\n"
	@printf "│                                                          │\n"
	@printf "│   No local backend, no AWS credentials needed.          │\n"
	@printf "│   make stop-all  to stop                                │\n"
	@printf "└──────────────────────────────────────────────────────────┘\n"
	@echo ""

# ── Backend only（直接跑 uvicorn，不用 Docker）────────────────────────────────
dev-api: check-dev
	@docker rm -f ship-api-local 2>/dev/null || true
	@pkill -f "uvicorn app:app" 2>/dev/null || true
	@cd backend-api && \
		AWS_REGION=$(AWS_REGION) \
		AWS_DEFAULT_REGION=$(AWS_REGION) \
		AWS_ACCESS_KEY_ID=$$(aws configure get aws_access_key_id --profile $(AWS_PROFILE)) \
		AWS_SECRET_ACCESS_KEY=$$(aws configure get aws_secret_access_key --profile $(AWS_PROFILE)) \
		AWS_SESSION_TOKEN=$$(aws configure get aws_session_token --profile $(AWS_PROFILE)) \
		VESSEL_TABLE=ship-analysis-dev-vessel-data \
		MAINT_TABLE=ship-analysis-dev-maintenance-events \
		FLEET_SUMMARY_TABLE=ship-analysis-dev-fleet-summary \
		FUEL_ANOMALY_TABLE=ship-analysis-dev-fuel-anomaly-cause \
		$(VENV_UVICORN) app:app --host 0.0.0.0 --port $(API_PORT) > /tmp/backend-api.log 2>&1 &
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
		if curl -fsS http://127.0.0.1:$(API_PORT)/health >/dev/null; then \
			echo "✅  Backend running at http://localhost:$(API_PORT)"; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "ERROR: Backend did not become healthy within 30 seconds. /tmp/backend-api.log:"; \
	cat /tmp/backend-api.log; \
	exit 1

# ── Frontend only ─────────────────────────────────────────────────────────────
dev-frontend: check-dev
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
	@echo "▶  Updating ECS service to new task definition..."
	@NEW_ARN=$$(aws ecs register-task-definition \
		--profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--cli-input-json file:///tmp/ship-api-taskdef.json \
		--query 'taskDefinition.taskDefinitionArn' --output text) && \
		echo "  Registered: $$NEW_ARN" && \
		aws ecs update-service \
			--profile $(AWS_PROFILE) --region $(AWS_REGION) \
			--cluster $(ECS_CLUSTER) \
			--service $(ECS_BACKEND_SVC) \
			--task-definition "$$NEW_ARN" \
			--force-new-deployment \
			--query 'service.deployments[0].{status:status,desired:desiredCount}' \
			--output table
	@echo "▶  Stopping old running tasks to free port 8000 (host-network mode)..."
	@OLD_TASKS=$$(aws ecs list-tasks \
		--profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--cluster $(ECS_CLUSTER) \
		--output text --query 'taskArns[*]' 2>/dev/null) && \
	if [ -n "$$OLD_TASKS" ]; then \
		for TASK in $$OLD_TASKS; do \
			echo "  Stopping task: $$TASK"; \
			aws ecs stop-task \
				--profile $(AWS_PROFILE) --region $(AWS_REGION) \
				--cluster $(ECS_CLUSTER) \
				--task "$$TASK" \
				--reason "Forced by make prod — free port for new deployment" \
				--query 'task.lastStatus' --output text 2>/dev/null || true; \
		done; \
	else \
		echo "  No running tasks to stop"; \
	fi
	@echo "▶  Waiting for new task to become healthy..."
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12; do \
		sleep 10; \
		STATUS=$$(curl -sf http://52.45.130.183:8000/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null); \
		if [ "$$STATUS" = "ok" ]; then \
			echo "✅  Backend healthy after $$((i*10))s → $(BACKEND_CF_URL)/health"; \
			break; \
		fi; \
		echo "  Waiting... ($$((i*10))s)"; \
	done

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
