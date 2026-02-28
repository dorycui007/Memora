.PHONY: local backend frontend install docker down

# Run both backend and frontend locally
local: backend frontend

backend:
	cd backend && .venv/bin/uvicorn memora.api.app:app --reload --port 8000 &

frontend:
	cd frontend && npm run dev &

# Install dependencies
install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

# Run with Docker
docker:
	docker compose up --build

# Stop Docker containers
down:
	docker compose down

# Stop background processes
stop:
	-pkill -f "uvicorn memora.api.app:app" 2>/dev/null
	-pkill -f "vite" 2>/dev/null
