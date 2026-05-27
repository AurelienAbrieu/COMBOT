# COMBOT - Carrier Operation Manager Assistant

AI-powered chatbot assistant for Quadient smart locker **Carrier Operation Managers**.

Built with the same architecture as PM Chatbot v2, adapted for the carrier operations segment.

## Features

- **Locker Status** - Check locker status by device ID (active/inactive, blocked boxes, expired parcels)
- **Parcel Tracking** - Look up parcel status by tracking number
- **Pickup Codes** - View and resend pickup codes (by parcel number or recipient name)
- **Nearby Lockers** - Find available lockers near GPS coordinates
- **Courier Management** - Add or remove couriers/delivery agents
- **Report Generation** - Generate and send reports by email (parcel drops, occupation rates, etc.)

## Architecture

```
COMBOT/
  web_app.py            # Root entry point (imports from src/)
  main.py               # CLI entry point
  src/com_chatbot/
    web_app.py           # FastAPI app (CSRF, rate limiting, SSE streaming)
    chat_engine.py       # Unified chat engine (CLI + web)
    agent.py             # Claude agent config + system prompt + tool registry
    pmd_client.py        # Session-aware PMD HTTP client
    settings.py          # Typed settings (pydantic-settings)
    request_context.py   # Correlation context (ContextVars)
    app_logging.py       # Structured rotating logs
    tools_status.py      # Locker status + parcel status tools
    tools_pickup.py      # View/resend pickup code tools
    tools_lockers.py     # Find nearby lockers tool
    tools_couriers.py    # Add/remove courier tools
    tools_reports.py     # Report generation tool
    ui/                  # Web UI (single HTML file)
    data/                # Static data files
  tests/
    e2e/                 # Playwright E2E tests
    unit/                # Unit/regression tests
  infra/
    docker/              # Dockerfile + docker-compose
    deploy/              # Release scripts
```

## Quick Start

### Prerequisites
- Python 3.12+
- AWS credentials configured for Bedrock access
- PMD API credentials

### Setup

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Run (Web)

```bash
python -m uvicorn web_app:app --host 127.0.0.1 --port 8000 --reload
```

Open http://127.0.0.1:8000 in your browser.

### Run (CLI)

```bash
python main.py
```

### Run Tests

```bash
# E2E tests (start server first)
pytest tests/e2e/ --headed -v

# Unit tests
pytest tests/unit/ -v
```

## UI

The web UI uses a **teal/cyan** color scheme (vs amber for PM Chatbot) to visually distinguish the Carrier Operation Manager role. No cards - responses are displayed as raw text from the LLM.

## Differences from PM Chatbot v2

| Aspect | PM Chatbot v2 | COMBOT |
|--------|---------------|--------|
| Target user | Property Manager | Carrier Operation Manager |
| UI accent color | Amber (#f59e0b) | Cyan (#06b6d4) |
| Card rendering | Yes (resident, parcel, history, plan cards) | No (raw text) |
| Sidebar / Locker map | Yes | No |
| Tools | 25 (residents, parcels, lockers, FAQ) | 8 (status, pickup, lockers, couriers, reports) |
| System prompt | PM-focused | Carrier-focused |
