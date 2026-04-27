from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent import run_chat
from database import create_interaction, get_all_interactions, get_session, init_db, serialize_interaction


app = FastAPI(title="AI-First CRM HCP Module")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


class ManualLogRequest(BaseModel):
    hcp_name: str = Field(..., min_length=1)
    interaction_date: date | str
    interaction_type: str = Field(default="Form")
    summary: str = Field(..., min_length=1)


@app.on_event("startup")
def startup() -> None:
    init_db()


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


@app.post("/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    return run_chat(payload.message, payload.session_id)


@app.post("/manual-log")
def manual_log(payload: ManualLogRequest) -> dict[str, Any]:
    interaction_date = _parse_date(payload.interaction_date)
    with get_session() as session:
        record = create_interaction(
            session,
            hcp_name=payload.hcp_name,
            interaction_date=interaction_date,
            interaction_type=payload.interaction_type,
            summary=payload.summary,
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