# CRM Backend API

FastAPI-powered backend with LangGraph AI agent, PostgreSQL database, and Groq LLM integration.

## File Structure

```
crm-backend/
├── main.py           # FastAPI app with CORS & routes
├── agent.py          # LangGraph agent with Groq (llama-3.1-8b-instant)
├── database.py       # SQLAlchemy ORM & models
├── requirements.txt  # Python dependencies
├── .env             # Environment variables (never commit)
└── .gitignore
```

## Setup

```bash
# 1. Create virtual environment
python -m venv venv

# 2. Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env with your API keys
# See .env.example for format

# 5. Run the server
uvicorn main:app --reload
```

Server runs on: `http://localhost:8000`

## Environment Variables (.env)

```env
GROQ_API_KEY=gsk_...
DATABASE_URL=postgresql://user:password@host:5432/db
GROQ_MODEL=llama-3.1-8b-instant  # Optional, defaults to llama-3.1-8b-instant
```

## API Routes

- `POST /chat` - Send message to AI agent
- `POST /manual-log` - Log interaction to database
- `GET /history/{hcp_name}` - Get interaction history
- `GET /health` - Health check

## Key Features

- ✅ CORS enabled for frontend (ports 5173)
- ✅ Retry logic for Groq rate limits (2s delay, 3 attempts)
- ✅ Fallback responses on failure
- ✅ PostgreSQL with SQLAlchemy ORM
- ✅ LangGraph for AI orchestration
- ✅ Structured interaction extraction

## Testing

```bash
# Direct test of chat function
python -c "from agent import run_chat; print(run_chat('test', 'session_id'))"
```
