.PHONY: install run ngrok dev build up down logs pending approve \
        nightly-report nightly-report-agent \
        issue-triager issue-triager-agent \
        lint format check pre-commit install-hooks \
        pr pr-list pr-view pr-merge

# ── Dev ───────────────────────────────────────────────────────────────────────

NGROK_DOMAIN ?= jockey-drum-sloped.ngrok-free.dev

install:
	uv sync

lint:
	uv run ruff check .

format:
	uv run ruff format .

check:
	uv run ruff check . && uv run ruff format --check .

pre-commit: check
	@echo "✓ All checks passed — safe to commit."

install-hooks:
	@echo '#!/bin/sh\nmake pre-commit' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "✓ pre-commit hook installed. Runs 'make pre-commit' on every git commit."

run:
	uv run python3 -u gateway/server.py

ngrok:
	ngrok http --domain=$(NGROK_DOMAIN) 8000

dev:
	@echo "Starting gateway and ngrok in parallel..."
	@trap 'kill 0' INT; \
	uv run python3 -u gateway/server.py & \
	ngrok http --domain=$(NGROK_DOMAIN) 8000 --log=stdout & \
	wait

# ── Pull Requests ─────────────────────────────────────────────────────────────

pr: pre-commit
	gh pr create --fill

pr-list:
	gh pr list

pr-view:
	gh pr view --web

pr-merge:
	gh pr merge --squash --delete-branch

# ── Docker ────────────────────────────────────────────────────────────────────

build:
	docker build -t mcp-gateway .

up:
	docker run --env-file .env -p 8000:8000 --name mcp-gateway mcp-gateway

down:
	docker stop mcp-gateway && docker rm mcp-gateway

logs:
	docker logs -f mcp-gateway

# ── Approval ──────────────────────────────────────────────────────────────────
# Usage: make approve THREAD=<thread_id> DECISION=approve|reject

pending:
	uv run python3 scripts/approve.py --list 2>/dev/null || curl -s http://localhost:8000/pending | python3 -m json.tool

approve:
	uv run python3 scripts/approve.py $(THREAD) $(DECISION)

# ── Scripts ───────────────────────────────────────────────────────────────────

nightly-report:
	uv run python3 scripts/nightly_report.py

nightly-report-agent:
	uv run python3 agents/nightly_report_agent.py

issue-triager:
	uv run python3 scripts/issue_triager.py

issue-triager-agent:
	uv run python3 agents/issue_triager_agent.py
