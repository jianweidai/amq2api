# Project Structure

```
amq2api/
├── run.py                     # Entry point script (imports from src.main)
├── pyproject.toml             # Python project configuration (pytest settings)
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Docker image build
├── docker-compose.yml         # Docker Compose config
├── start.sh                   # Local startup script
│
├── src/                       # Source code directory
│   ├── __init__.py
│   ├── main.py               # FastAPI server, API endpoints
│   ├── config.py             # Configuration management, token caching
│   ├── models.py             # Pydantic/dataclass models for Claude & CodeWhisperer
│   │
│   ├── data/                 # Database files
│   │   └── accounts.db       # SQLite database
│   │
│   ├── auth/                 # Authentication module
│   │   ├── __init__.py
│   │   ├── auth.py          # Amazon Q token management and refresh
│   │   ├── account_manager.py # Multi-account management (SQLite/MySQL)
│   │   └── token_scheduler.py # Scheduled token refresh
│   │
│   ├── amazonq/              # Amazon Q backend module
│   │   ├── __init__.py
│   │   ├── converter.py     # Request conversion (Claude → Amazon Q)
│   │   ├── parser.py        # Event parsing (Amazon Q → Claude)
│   │   ├── event_stream_parser.py # AWS Event Stream binary format parser
│   │   └── stream_handler.py # Streaming response handler
│   │
│   ├── processing/           # Common processing module
│   │   ├── __init__.py
│   │   ├── message_processor.py # History message merging
│   │   ├── model_mapper.py  # Model name mapping between providers
│   │   ├── cache_manager.py # Prompt caching simulation
│   │   └── usage_tracker.py # Token usage tracking
│   │
│   ├── gemini/               # Gemini backend module
│   │   ├── __init__.py
│   │   ├── auth.py          # Gemini token management
│   │   ├── converter.py     # Request conversion (Claude → Gemini)
│   │   ├── handler.py       # Gemini streaming response handler
│   │   ├── models.py        # Gemini data models
│   │   └── oauth_client.py  # Gemini OAuth client
│   │
│   └── custom_api/           # Custom API backend module
│       ├── __init__.py
│       ├── converter.py     # Format conversion (Claude ↔ OpenAI)
│       └── handler.py       # Custom API request handler
│
├── tests/                     # Test files directory
│   ├── __init__.py
│   ├── conftest.py           # Shared pytest fixtures
│   └── test_*.py             # Test files (pytest)
│
├── docs/                      # Documentation
│   ├── API_DETAILS.md
│   ├── BUGFIXES.md
│   ├── CHANGELOG.md
│   └── DOCKER_DEPLOY.md
│
└── frontend/                  # Web UI
    ├── index.html            # Admin management interface
    ├── donate.html           # Gemini account donation page
    └── oauth-callback-page.html
```

## Request Flow

```
Claude API Request
    ↓
src/main.py (FastAPI endpoint)
    ↓
Smart routing (Amazon Q / Gemini / Custom API)
    ↓
src/amazonq/converter.py (format conversion)
    ↓
Backend API call
    ↓
src/amazonq/event_stream_parser.py / src/gemini/handler.py (response parsing)
    ↓
src/amazonq/stream_handler.py (SSE generation)
    ↓
Claude SSE Response
```

## Module Responsibilities

- **src/main.py**: Entry point, routing logic, endpoint handlers
- **src/auth/**: Authentication and account management
- **src/amazonq/**: Amazon Q specific conversion and streaming
- **src/processing/**: Common utilities (caching, usage tracking, message processing)
- **src/gemini/**: Gemini-specific streaming and format conversion
- **src/custom_api/**: OpenAI/Claude format API proxying

## Import Convention

All internal imports use the `src.` prefix with module paths:
```python
from src.config import read_global_config
from src.models import ClaudeRequest
from src.auth.auth import get_auth_headers_with_retry
from src.auth.account_manager import get_random_account
from src.amazonq.converter import convert_claude_to_codewhisperer_request
from src.amazonq.stream_handler import handle_amazonq_stream
from src.processing.cache_manager import CacheManager
from src.gemini.handler import handle_gemini_stream
```
