.PHONY: local install docker down stop

# Run locally
local:
	.venv/bin/uvicorn memora.api.app:app --reload --port 8000 &

# Install dependencies
install:
	python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Run with Docker
docker:
	docker compose up --build

# Stop Docker containers
down:
	docker compose down

# Stop background processes
stop:
	-pkill -f "uvicorn memora.api.app:app" 2>/dev/null
