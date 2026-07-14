.PHONY: dev dev-api dev-frontend stop predict clean

# AWS profile for hackathon credentials
AWS_PROFILE ?= hackathon
API_PORT    ?= 8000
DOCKER_IMAGE = ship-analysis-api:local

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
