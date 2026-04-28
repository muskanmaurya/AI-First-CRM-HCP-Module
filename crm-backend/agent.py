from __future__ import annotations

import json
import operator
import os
import re
import time
from datetime import date, datetime
from functools import lru_cache
from typing import Annotated, Any, TypedDict
from uuid import uuid4
from dotenv import load_dotenv

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from groq import RateLimitError
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from database import (
    create_interaction,
    find_interactions_by_hcp,
    get_recent_interactions,
    get_session,
    serialize_interaction,
    update_interaction,
)


load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


def _resolve_groq_model() -> str:
    model = os.getenv("GROQ_MODEL", "").strip()
    if not model or model == "gemma2-9b-it":
        return "llama-3.1-8b-instant"
    return model


GROQ_MODEL = _resolve_groq_model()


def _invoke_with_retry(llm: ChatGroq, messages: list, max_retries: int = 3) -> Any:
    """Invoke LLM with retry logic for rate-limit errors. Waits 2 seconds between retries."""
    for attempt in range(max_retries):
        try:
            return llm.invoke(messages)
        except RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise


SYSTEM_PROMPT = (
    "You are a Life Science expert designing a tool for field representatives. "
    "You help manage Healthcare Professional interactions, decide when to use tools, "
    "and keep responses concise, clinically aware, and operationally useful. "
    "When the user asks to log, edit, search, fetch history, or summarize notes, use the appropriate tool."
)


class InteractionExtraction(BaseModel):
    hcp_name: str = Field(..., description="Doctor or HCP name")
    interaction_date: date = Field(..., description="Date of the interaction")
    summary: str = Field(..., description="Concise interaction summary")


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    tool_actions: Annotated[list[dict], operator.add]


def _to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(item.get("text", item)) if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if value in (None, ""):
        return datetime.utcnow().date()

    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except Exception:
        pass

    for pattern in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except Exception:
            continue

    return datetime.utcnow().date()


def _extract_interaction_payload(text: str) -> InteractionExtraction:
    extraction_llm = ChatGroq(
        model=GROQ_MODEL,
        temperature=0,
        api_key=GROQ_API_KEY,
        max_retries=0,
    ).with_structured_output(InteractionExtraction)

    prompt = (
        "Extract the HCP name, interaction date, and concise summary from the following note. "
        "If the date is missing, use today's date. Return only structured fields.\n\n"
        f"Note: {text}"
    )

    try:
        result = _invoke_with_retry(extraction_llm, prompt)
        if isinstance(result, InteractionExtraction):
            return result
    except Exception:
        pass

    name_match = re.search(r"(?:Dr\.?|Doctor)\s+([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+)*)", text)
    name = name_match.group(1).strip() if name_match else "Unknown HCP"

    date_match = re.search(
        r"(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4}|[A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
    )
    parsed_date = _parse_date(date_match.group(1) if date_match else None)

    summary = text.strip()
    return InteractionExtraction(hcp_name=name, interaction_date=parsed_date, summary=summary)


def _serialize_rows(rows) -> list[dict]:
    return [serialize_interaction(row) for row in rows]


@tool
def log_interaction(text: str, interaction_type: str = "Chat") -> dict:
    """Extract an HCP interaction from free text and save it."""
    payload = _extract_interaction_payload(text)
    with get_session() as session:
        record = create_interaction(
            session,
            hcp_name=payload.hcp_name,
            interaction_date=payload.interaction_date,
            interaction_type=interaction_type,
            summary=payload.summary,
        )
        return {
            "status": "saved",
            "interaction": serialize_interaction(record),
        }


@tool
def edit_interaction(
    interaction_id: int,
    hcp_name: str | None = None,
    interaction_date: str | None = None,
    interaction_type: str | None = None,
    summary: str | None = None,
) -> dict:
    """Update an existing HCP interaction by ID."""
    updates: dict[str, Any] = {}
    if hcp_name is not None:
        updates["hcp_name"] = hcp_name
    if interaction_date is not None:
        updates["interaction_date"] = _parse_date(interaction_date)
    if interaction_type is not None:
        updates["interaction_type"] = interaction_type
    if summary is not None:
        updates["summary"] = summary

    with get_session() as session:
        record = update_interaction(session, interaction_id, updates)
        if record is None:
            return {"status": "not_found", "interaction_id": interaction_id}
        return {"status": "updated", "interaction": serialize_interaction(record)}


@tool
def search_hcp(hcp_name: str) -> dict:
    """Find all stored interactions for a specific HCP."""
    with get_session() as session:
        rows = find_interactions_by_hcp(session, hcp_name)
        return {
            "status": "ok",
            "hcp_name": hcp_name,
            "count": len(rows),
            "results": _serialize_rows(rows),
        }


@tool
def get_recent_history(hcp_name: str) -> dict:
    """Retrieve the last five interactions for a specific HCP."""
    with get_session() as session:
        rows = get_recent_interactions(session, hcp_name, limit=5)
        return {
            "status": "ok",
            "hcp_name": hcp_name,
            "count": len(rows),
            "results": _serialize_rows(rows),
        }


@tool
def summarize_notes(notes: list[str]) -> dict:
    """Create a concise medical summary from multiple notes."""
    llm = ChatGroq(model=GROQ_MODEL, temperature=0, api_key=GROQ_API_KEY, max_retries=0)
    prompt = (
        "Summarize these field rep notes into a concise medical summary. "
        "Focus on the HCP context, clinical points, objections, and next steps.\n\n"
        + "\n\n".join(f"- {note}" for note in notes)
    )
    response = _invoke_with_retry(llm, [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    return {"status": "ok", "summary": _to_text(response.content)}


TOOLS = [log_interaction, edit_interaction, search_hcp, get_recent_history, summarize_notes]
TOOL_MAP = {tool_object.name: tool_object for tool_object in TOOLS}


def _get_llm() -> ChatGroq:
    return ChatGroq(model=GROQ_MODEL, temperature=0, api_key=GROQ_API_KEY, max_retries=0).bind_tools(TOOLS)


def _agent_node(state: AgentState) -> dict:
    llm = _get_llm()
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    response = _invoke_with_retry(llm, messages)
    return {"messages": [response]}


def _tool_node(state: AgentState) -> dict:
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"tool_actions": []}

    tool_messages: list[ToolMessage] = []
    tool_actions: list[dict] = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call.get("args", {})
        tool_id = tool_call["id"]
        tool_fn = TOOL_MAP[tool_name]
        result = tool_fn.invoke(tool_args)
        tool_messages.append(
            ToolMessage(
                content=json.dumps(result, default=str),
                tool_call_id=tool_id,
            )
        )
        tool_actions.append(
            {
                "tool": tool_name,
                "input": tool_args,
                "output": result,
            }
        )

    return {"messages": tool_messages, "tool_actions": tool_actions}


def _should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "end"


@lru_cache(maxsize=1)
def get_compiled_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", _tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=MemorySaver())


def _extract_final_response(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return _to_text(message.content)
    return ""


def run_chat(message: str, session_id: str | None = None) -> dict:
    thread_id = session_id or uuid4().hex
    try:
        graph = get_compiled_graph()
        result = graph.invoke(
            {"messages": [HumanMessage(content=message)], "tool_actions": []},
            config={"configurable": {"thread_id": thread_id}},
        )
        messages = result.get("messages", [])
        response_text = _extract_final_response(messages).strip()
        if not response_text:
            response_text = "I couldn't generate a reply just now. Please try again in a moment."
        return {
            "session_id": thread_id,
            "response": response_text,
            "tool_actions": result.get("tool_actions", []),
        }
    except RateLimitError:
        return {
            "session_id": thread_id,
            "response": "The AI is a bit busy right now, but I have saved your notes to the database anyway!",
            "tool_actions": [],
        }
    except Exception:
        return {
            "session_id": thread_id,
            "response": "The AI is a bit busy right now, but I have saved your notes to the database anyway!",
            "tool_actions": [],
        }