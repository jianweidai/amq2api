# Tech Stack

## Language & Runtime
- Python 3.11+
- Async/await patterns throughout

## Web Framework
- FastAPI with uvicorn server
- CORS middleware enabled
- SSE (Server-Sent Events) streaming

## HTTP Client
- httpx for async HTTP requests

## Database
- SQLite (default) - `accounts.db`
- MySQL (optional) - for multi-instance deployments

## Key Libraries
- `pydantic` - Data validation and models
- `python-dotenv` - Environment variable management
- `tiktoken` - Token counting
- `pymysql` - MySQL support (optional)

## Testing
- `pytest` with `pytest-asyncio`
- `hypothesis` for property-based testing

## Deployment
- Docker with docker-compose
- Shell script (`start.sh`) for local development

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python3 main.py
# or
./start.sh

# Run all tests
pytest

# Run specific test file
pytest test_basic.py

# Run tests with verbose output
pytest -v

# Health check
curl http://localhost:8080/health
```

## Environment Variables

Required:
- `AMAZONQ_REFRESH_TOKEN` - Amazon Q refresh token
- `AMAZONQ_CLIENT_ID` - Client ID
- `AMAZONQ_CLIENT_SECRET` - Client secret

Optional:
- `PORT` - Server port (default: 8080)
- `ADMIN_KEY` - Admin panel authentication
- `API_KEY` - API authentication
- `ENABLE_CACHE_SIMULATION` - Enable prompt caching simulation
- `ENABLE_AUTO_REFRESH` - Enable scheduled token refresh
