from __future__ import annotations

import json
import re
import uuid
import logging
import os
from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError

from agent import run_chat
from database import (
    create_interaction,
    get_all_interactions,
    get_session,
    init_db,
    serialize_interaction,
    create_chat_session,
    get_all_sessions,
    create_chat_message,
    get_messages_for_session,
)
from database import ChatSession


logger = logging.getLogger(__name__)


def _get_cors_origins() -> list[str]:
    env_origins = os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_URL")
    origins = [
        "http://localhost:5173",
        "http://localhost:10000", # Add this based on your logs
        "http://127.0.0.1:5173",
        "https://ai-first-crm-hcp-module-1.onrender.com",
    ]

    if env_origins:
        origins.extend([origin.strip() for origin in env_origins.split(",") if origin.strip()])

    vercel_url = os.getenv("VERCEL_URL")
    if vercel_url:
        vercel_origin = vercel_url if vercel_url.startswith("http") else f"https://{vercel_url}"
        origins.append(vercel_origin)

    return list(dict.fromkeys(origins))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("SKIP_DB_INIT_ON_STARTUP", "false").lower() == "true":
        logger.warning("Skipping init_db() on startup because SKIP_DB_INIT_ON_STARTUP=true")
        yield
        return

    try:
        init_db()
    except OperationalError:
        logger.exception("Database initialization failed; starting app without eager schema creation.")
    except Exception:
        logger.exception("Unexpected database initialization error; continuing startup.")
    yield


app = FastAPI(title="AI-First CRM HCP Module", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


class InteractionCreate(BaseModel):
    hcp_name: str | None = None
    interaction_date: date | str | None = None
    interaction_type: str | None = None
    time: str | None = None
    attendees: str | None = None
    topics: str | None = None
    materials: list[str] | str | None = None
    samples: list[str] | str | None = None
    sentiment: str | None = None
    outcomes: str | None = None
    follow_up: str | None = None
    summary: str | None = None


ManualLogRequest = InteractionCreate


# init_db is handled by the FastAPI lifespan above


def _parse_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid interaction_date: {value}") from exc


def _normalize_text_list(value: list[str] | str | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned or None
    cleaned = [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]
    return cleaned or None


def _build_summary(payload: InteractionCreate, interaction_date: date) -> str:
    parts = []
    if payload.hcp_name:
        parts.append(f"HCP: {payload.hcp_name}")
    parts.append(f"Date: {interaction_date.isoformat()}")
    if payload.interaction_type:
        parts.append(f"Type: {payload.interaction_type}")
    if payload.time:
        parts.append(f"Time: {payload.time}")
    if payload.attendees:
        parts.append(f"Attendees: {payload.attendees}")
    if payload.topics:
        parts.append(f"Topics: {payload.topics}")
    materials = _normalize_text_list(payload.materials)
    if materials:
        parts.append(f"Materials: {', '.join(materials)}")
    samples = _normalize_text_list(payload.samples)
    if samples:
        parts.append(f"Samples: {', '.join(samples)}")
    if payload.sentiment:
        parts.append(f"Sentiment: {payload.sentiment}")
    if payload.outcomes:
        parts.append(f"Outcomes: {payload.outcomes}")
    if payload.follow_up:
        parts.append(f"Follow-up: {payload.follow_up}")
    return " | ".join(parts) or "Interaction logged."


@app.post("/chat")

def chat(payload: ChatRequest) -> dict[str, Any]:
    # ensure session exists (create when missing)
    session_id = payload.session_id
    with get_session() as db:
        if not session_id:
            # create a new session with a generic title

            session_id = uuid.uuid4().hex
            # generate a better title from the first user message
            def _generate_title_from_message(msg: str) -> str:

                # Try to find patterns like 'Dr. Name' or 'Doctor Name'
                m = re.search(r"(?:Dr\.?|Doctor)\s+([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+)*)", msg)
                if m:
                    name = m.group(1).strip()
                    return f"Meeting with Dr. {name}"

                # fallback: first 5 words
                words = msg.strip().split()
                title = " ".join(words[:5])
                return f"Chat: {title}" if title else f"Chat {session_id[:8]}"

            title = _generate_title_from_message(payload.message or "")
            create_chat_session(db, session_id=session_id, title=title)

        # save user message
        create_chat_message(db, session_id=session_id, role="user", content=payload.message)

    # call the agent
    result = run_chat(payload.message, session_id)

    # save assistant response
    assistant_text = result.get("response", "")
    with get_session() as db:
        create_chat_message(db, session_id=session_id, role="assistant", content=assistant_text)

    return {"session_id": session_id, **result}


@app.post("/sessions")
def create_session(payload: dict) -> dict[str, Any]:
    # Accepts optional session_id and title
    session_id = payload.get("session_id")
    title = payload.get("title") or "New Chat"
    if not session_id:
        import uuid

        session_id = uuid.uuid4().hex

    with get_session() as db:
        # create only if not exists
        existing = db.get(ChatSession, session_id)
        if existing is None:
            create_chat_session(db, session_id=session_id, title=title)

    return {"status": "created", "session_id": session_id, "title": title}


@app.get("/sessions")
def list_sessions() -> dict[str, Any]:
    with get_session() as db:
        sessions = get_all_sessions(db)
        return {"sessions": [{"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()} for s in sessions]}


@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str) -> dict[str, Any]:
    with get_session() as db:
        messages = get_messages_for_session(db, session_id)
        return {"messages": [{"id": m.id, "role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in messages]}


@app.post("/manual-log")
def manual_log(payload: InteractionCreate) -> dict[str, Any]:
    if not payload.hcp_name or not payload.hcp_name.strip():
        raise HTTPException(status_code=400, detail="HCP Name is required")
    if not payload.interaction_date:
        raise HTTPException(status_code=400, detail="Date is required")

    interaction_date = _parse_date(payload.interaction_date)
    materials = _normalize_text_list(payload.materials)
    samples = _normalize_text_list(payload.samples)
    summary = payload.summary or _build_summary(payload, interaction_date)
    with get_session() as session:
        record = create_interaction(
            session,
            hcp_name=payload.hcp_name,
            interaction_date=interaction_date,
            interaction_type=payload.interaction_type,
            time=payload.time,
            attendees=payload.attendees,
            topics=payload.topics,
            materials=materials,
            samples=samples,
            sentiment=payload.sentiment,
            outcomes=payload.outcomes,
            follow_up=payload.follow_up,
            summary=summary,
        )
        return {"status": "saved", "interaction": serialize_interaction(record)}


@app.get("/history/{hcp_name}")
def history(hcp_name: str) -> dict[str, Any]:
    with get_session() as session:
        records = get_all_interactions(session, hcp_name)
        return {
            "hcp_name": hcp_name,
            "count": len(records),
            "records": [serialize_interaction(record) for record in records],
        }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}