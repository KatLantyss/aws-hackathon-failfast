.PHONY: dev dev-api dev-frontend stop predict clean

# AWS profile for hackathon credentials
AWS_PROFILE ?= hackathon
API_PORT    ?= 8000
DOCKER_IMAGE = ship-analysis-api:local

# ── Dev（同時啟動 backend + frontend）─────────────────────────────────────────
# 使用方式：make dev
dev:
	@echo "Starting backend API (Docker) on port $(API_PORT)..."
	@$(MAKE) dev-api
	@echo ""
	@echo "Starting frontend dev server..."
	@$(MAKE) dev-frontend

# ── Backend only（Docker container）─────────────────────────────────────────
dev-api:
	@# 先停掉舊的同名 container（如果有的話）
	@docker rm -f ship-api-local 2>/dev/null || true
	@docker run -d \
		--name ship-api-local \
		-p $(API_PORT):8000 \
		-e AWS_REGION=us-east-1 \
		-e AWS_ACCESS_KEY_ID=$$(aws configure get aws_access_key_id --profile $(AWS_PROFILE)) \
		-e AWS_SECRET_ACCESS_KEY=$$(aws configure get aws_secret_access_key --profile $(AWS_PROFILE)) \
		-e AWS_SESSION_TOKEN=$$(aws configure get aws_session_token --profile $(AWS_PROFILE)) \
		-e VESSEL_TABLE=ship-analysis-dev-vessel-data \
		-e MAINT_TABLE=ship-analysis-dev-maintenance-events \
		$(DOCKER_IMAGE)
	@echo "✅  Backend running at http://localhost:$(API_PORT)"
	@echo "    Health: $$(sleep 2 && curl -s http://localhost:$(API_PORT)/health)"

# ── Frontend only ─────────────────────────────────────────────────────────────
dev-frontend:
	@cd frontend && \
		VITE_BACKEND_BASE_URL=http://localhost:$(API_PORT) \
		npm run dev

# ── Stop backend container ────────────────────────────────────────────────────
stop:
	@docker rm -f ship-api-local 2>/dev/null && echo "✅  Backend stopped" || echo "No backend container running"

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
