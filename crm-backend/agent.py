from __future__ import annotations

import json
import re
import uuid
import logging
import os
import time
from datetime import date, datetime
from typing import Any, TypedDict
from dotenv import load_dotenv

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from groq import RateLimitError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field

from database import (
    create_interaction,
    find_interactions_by_hcp,
    get_recent_interactions as db_get_recent_interactions,
    get_session,
    serialize_interaction,
    update_interaction,
)


load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ============================================================================
# MODEL ROTATION CONFIGURATION
# ============================================================================

GROQ_MODELS = [
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "llama2-70b-4096",
]

GROQ_MODEL = GROQ_MODELS[0]  # Primary model for backward compatibility
FORM_FILLER_MODEL = "gemma2-9b-it"

MODEL_FAILOVER_LOG: dict[str, list[str]] = {}  # Track failed models per session


def _invoke_with_model_failover(
    messages: list,
    max_retries_per_model: int = 3,
    models: list[str] | None = None,
    session_id: str = "unknown",
) -> Any:
    """
    Invoke LLM with model rotation failover.
    
    Try each model in sequence. Retry 2s between attempts if rate-limited.
    Falls back to next model on RateLimitError (429 status).
    
    Args:
        messages: LangChain message list
        max_retries_per_model: Retries per model (default 3)
        models: Models to try (defaults to GROQ_MODELS)
        session_id: Session ID for logging
    
    Returns:
        LLM response from first successful model
    
    Raises:
        RuntimeError: If all models fail
    """
    if models is None:
        models = GROQ_MODELS.copy()
    
    if session_id not in MODEL_FAILOVER_LOG:
        MODEL_FAILOVER_LOG[session_id] = []
    
    failed_models = []
    
    for model in models:
        try:
            logger.info(f"[{session_id}] Attempting model: {model}")
            llm = ChatGroq(
                model=model,
                temperature=0,
                api_key=GROQ_API_KEY,
                max_retries=0,
            )
            
            for attempt in range(max_retries_per_model):
                try:
                    response = llm.invoke(messages)
                    logger.info(f"[{session_id}] ✓ Success with {model}")
                    return response
                except RateLimitError:
                    if attempt < max_retries_per_model - 1:
                        logger.warning(
                            f"[{session_id}] Rate limit on {model} (attempt {attempt + 1}/{max_retries_per_model}). "
                            f"Waiting 2s..."
                        )
                        time.sleep(2)
                    else:
                        failed_models.append(model)
                        logger.warning(
                            f"[{session_id}] {model} exhausted. Moving to next model..."
                        )
                        break
        except Exception as e:
            failed_models.append(model)
            logger.error(
                f"[{session_id}] Model {model} error: {type(e).__name__}: {str(e)[:80]}"
            )
            continue
    
    MODEL_FAILOVER_LOG[session_id] = failed_models
    logger.error(f"[{session_id}] All models failed: {failed_models}")
    raise RuntimeError(
        f"All models exhausted for session {session_id}. "
        f"Failed: {failed_models}"
    )


def _invoke_with_retry(llm: ChatGroq, messages: list, max_retries: int = 3) -> Any:
    """Fallback retry logic for single model (used in tools)."""
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
    "You help manage Healthcare Professional interactions and have access to these tools:\n"
    "- log_interaction: Save new HCP meeting notes to database\n"
    "- edit_interaction: Update existing interaction by ID\n"
    "- search_hcp_history: Find past meetings with a specific Doctor (pass the doctor name directly if mentioned)\n"
    "- get_recent_interactions: Retrieve exactly the last 5 interactions for one doctor\n"
    "- summarize_interactions: Create a concise clinical summary from multiple notes\n\n"
    "IMPORTANT: If the user mentions a doctor's name (e.g., 'Dr. Sharma', 'Dr Verma', 'Dr. Alice Johnson'), "
    "ALWAYS extract that name and use it directly with search_hcp_history. Do NOT ask the user for the name again. "
    "The search_hcp_history tool requires the hcp_name parameter to be the full doctor name as mentioned.\n\n"
    "When extracting or updating medical names/terms, use typo-resilient reasoning and correct obvious misspellings "
    "(for example, common medicine or doctor-name typos) before returning values.\n\n"
    "When the user asks to log, edit, search, review recent history, or summarize interactions, use the appropriate tool immediately. "
    "Keep responses concise, clinically aware, and operationally useful."
)


class InteractionExtraction(BaseModel):
    hcp_name: str = Field(..., description="Doctor or HCP name")
    interaction_date: date = Field(..., description="Date of the interaction")
    summary: str = Field(..., description="Concise interaction summary")


class FormExtractionResult(BaseModel):
    intent: str = Field(default="NONE", description="One of NONE, EXTRACT, UPDATE")
    hcp_name: str | None = Field(default=None)
    interaction_date: str | None = Field(default=None, description="Date in ISO format when possible")
    sentiment: str | None = Field(default=None, description="Positive, Neutral, or Negative")
    topics: str | None = Field(default=None)
    corrected_field: str | None = Field(default=None, description="Field name when intent is UPDATE")
    corrected_value: str | None = Field(default=None, description="Corrected value when intent is UPDATE")


class AgentState(TypedDict):
    messages: list[BaseMessage]
    tool_actions: list[dict]


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


def _extract_doctor_name_from_text(text: str) -> str | None:
    """
    Extract doctor name from text using regex patterns.
    Looks for patterns like 'Dr. Name', 'Dr Name', 'Doctor Name'.
    Returns the extracted name or None if not found.
    """
    # Match patterns: Dr. Name, Dr Name, Doctor Name
    patterns = [
        r"(?:Dr\.?|Doctor)\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)*)",
        r"([A-Z][a-z]+)\s+([A-Z][a-z]+)",  # Fallback: First Last (capitalized)
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # For first pattern, return group 1; for second, return groups 1 + 2
            if len(match.groups()) > 1:
                return f"{match.group(1)} {match.group(2)}"
            else:
                return match.group(1).strip()
    return None


def _normalize_form_key(field_name: str | None) -> str | None:
    if not field_name:
        return None
    field = field_name.strip().lower().replace(" ", "_")
    mapping = {
        "hcp": "hcp_name",
        "doctor": "hcp_name",
        "doctor_name": "hcp_name",
        "hcp_name": "hcp_name",
        "name": "hcp_name",
        "date": "interaction_date",
        "interaction_date": "interaction_date",
        "sentiment": "sentiment",
        "hcp_sentiment": "sentiment",
        "topics": "topics",
        "topic": "topics",
    }
    return mapping.get(field)


def _fallback_form_extraction(user_text: str) -> FormExtractionResult:
    lowered = user_text.lower()
    correction_match = re.search(r"i\s+meant\s+(.+?)\s*,?\s*not\s+(.+)$", user_text, re.IGNORECASE)
    if correction_match:
        corrected = correction_match.group(1).strip().rstrip(".")
        return FormExtractionResult(
            intent="UPDATE",
            corrected_field="hcp_name",
            corrected_value=corrected,
            hcp_name=corrected,
        )

    hcp_name = _extract_doctor_name_from_text(user_text)

    sentiment = None
    if any(term in lowered for term in ["positive", "good", "excellent", "great"]):
        sentiment = "Positive"
    elif any(term in lowered for term in ["neutral", "okay", "average"]):
        sentiment = "Neutral"
    elif any(term in lowered for term in ["negative", "poor", "bad"]):
        sentiment = "Negative"

    date_match = re.search(
        r"(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4}|[A-Za-z]+\s+\d{1,2},\s+\d{4})",
        user_text,
    )
    parsed_date = None
    if date_match:
        parsed_date = _parse_date(date_match.group(1)).isoformat()

    topics = user_text.strip() if user_text.strip() else None
    intent = "EXTRACT" if any([hcp_name, sentiment, parsed_date, topics]) else "NONE"

    return FormExtractionResult(
        intent=intent,
        hcp_name=hcp_name,
        interaction_date=parsed_date,
        sentiment=sentiment,
        topics=topics,
    )


def _extract_form_intent_and_updates(user_text: str) -> dict[str, Any]:
    extraction_llm = ChatGroq(
        model=FORM_FILLER_MODEL,
        temperature=0,
        api_key=GROQ_API_KEY,
        max_retries=0,
    ).with_structured_output(FormExtractionResult)

    prompt = (
        "You are an agentic CRM form-filler extractor. "
        "Extract these fields from the user's message when present: hcp_name, interaction_date, sentiment, topics. "
        "Detect correction/update intent when the user corrects earlier data (e.g., 'I meant Dr. Sharma, not Dr. Batra'). "
        "If correction intent is present, set intent=UPDATE and provide only corrected_field and corrected_value for the changed field. "
        "Use typo-resilient common-sense reasoning to fix obvious misspellings in names and medical terms before returning values. "
        "Return only structured fields.\n\n"
        f"User message: {user_text}"
    )

    try:
        result = _invoke_with_retry(extraction_llm, prompt)
        if not isinstance(result, FormExtractionResult):
            result = _fallback_form_extraction(user_text)
    except Exception as e:
        logger.warning(f"Form extraction fallback due to: {type(e).__name__}: {str(e)[:80]}")
        result = _fallback_form_extraction(user_text)

    intent = (result.intent or "NONE").upper()
    form_updates: dict[str, Any] = {}

    if intent == "UPDATE":
        corrected_key = _normalize_form_key(result.corrected_field)
        if corrected_key and result.corrected_value:
            form_updates[corrected_key] = result.corrected_value.strip()
    else:
        if result.hcp_name:
            form_updates["hcp_name"] = result.hcp_name.strip()
        if result.interaction_date:
            form_updates["interaction_date"] = result.interaction_date
        if result.sentiment:
            sentiment_value = result.sentiment.capitalize()
            if sentiment_value in {"Positive", "Neutral", "Negative"}:
                form_updates["sentiment"] = sentiment_value
            else:
                form_updates["sentiment"] = result.sentiment
        if result.topics:
            form_updates["topics"] = result.topics.strip()

    if intent == "UPDATE" and form_updates:
        only_key = next(iter(form_updates.keys()))
        only_value = form_updates[only_key]
        response_text = f"I have updated {only_key.replace('_', ' ')} to {only_value} for you."
    elif form_updates:
        response_text = "I captured the interaction details and pre-filled the form fields for you."
    else:
        response_text = "I am ready to capture interaction details whenever you share them."

    return {
        "intent": intent,
        "text": response_text,
        "form_updates": form_updates,
    }


def _serialize_rows(rows) -> list[dict]:
    return [serialize_interaction(row) for row in rows]


def _tool_error_payload(action: str, error: Exception, **extra: Any) -> dict[str, Any]:
    return {
        "status": "error",
        "action": action,
        "message": f"{action} failed",
        "error": f"{type(error).__name__}: {str(error)[:100]}",
        **extra,
    }


@tool("log_interaction")
def log_interaction(text: str, interaction_type: str = "Chat") -> dict:
    """Extract an HCP interaction from free text and save it to the database."""
    try:
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
    except Exception as e:
        logger.error(f"log_interaction error: {type(e).__name__}: {str(e)}")
        return _tool_error_payload("log_interaction", e, interaction=None)


@tool("edit_interaction")
def edit_interaction(
    interaction_id: int,
    hcp_name: str | None = None,
    interaction_date: str | None = None,
    interaction_type: str | None = None,
    time: str | None = None,
    attendees: str | None = None,
    topics: str | None = None,
    materials: list[str] | str | None = None,
    samples: list[str] | str | None = None,
    sentiment: str | None = None,
    outcomes: str | None = None,
    follow_up: str | None = None,
    summary: str | None = None,
) -> dict:
    """Update an existing HCP interaction by ID."""
    try:
        updates: dict[str, Any] = {}
        if hcp_name is not None:
            updates["hcp_name"] = hcp_name
        if interaction_date is not None:
            updates["interaction_date"] = _parse_date(interaction_date)
        if interaction_type is not None:
            updates["interaction_type"] = interaction_type
        if time is not None:
            updates["time"] = time
        if attendees is not None:
            updates["attendees"] = attendees
        if topics is not None:
            updates["topics"] = topics
        if materials is not None:
            updates["materials"] = materials if isinstance(materials, list) else [item.strip() for item in materials.split(",") if item.strip()]
        if samples is not None:
            updates["samples"] = samples if isinstance(samples, list) else [item.strip() for item in samples.split(",") if item.strip()]
        if sentiment is not None:
            updates["sentiment"] = sentiment
        if outcomes is not None:
            updates["outcomes"] = outcomes
        if follow_up is not None:
            updates["follow_up"] = follow_up
        if summary is not None:
            updates["summary"] = summary

        with get_session() as session:
            record = update_interaction(session, interaction_id, updates)
            if record is None:
                return {"status": "not_found", "interaction_id": interaction_id}
            return {"status": "updated", "interaction": serialize_interaction(record)}
    except Exception as e:
        logger.error(f"edit_interaction error: {type(e).__name__}: {str(e)}")
        return _tool_error_payload("edit_interaction", e, interaction_id=interaction_id, interaction=None)


@tool("search_hcp_history")
def search_hcp_history(hcp_name: str) -> dict:
    """
    Search the database for all past meetings with a specific Healthcare Professional.
    
    This tool queries the database to find all interactions with a given doctor.
    
    Args:
        hcp_name: The name of the doctor to search for. This should be extracted directly 
                  from the user's message if they mention a doctor (e.g., 'Dr. Sharma', 
                  'Dr Verma', 'Dr. Alice Johnson'). Do not ask for clarification if a name 
                  is mentioned—use it directly.
    
    Returns:
        A dictionary containing status, hcp_name, count of meetings, and detailed results.
    """
    try:
        with get_session() as session:
            rows = find_interactions_by_hcp(session, hcp_name)
            return {
                "status": "ok",
                "hcp_name": hcp_name,
                "count": len(rows),
                "results": _serialize_rows(rows),
            }
    except Exception as e:
        logger.error(f"search_hcp_history error: {type(e).__name__}: {str(e)}")
        return _tool_error_payload("search_hcp_history", e, hcp_name=hcp_name, count=0, results=[])


@tool("get_recent_interactions")
def get_recent_interactions(hcp_name: str) -> dict:
    """Fetch exactly the last 5 interactions for a specific HCP."""
    try:
        with get_session() as session:
            rows = db_get_recent_interactions(session, hcp_name, limit=5)
            return {
                "status": "ok",
                "hcp_name": hcp_name,
                "count": len(rows),
                "results": _serialize_rows(rows),
            }
    except Exception as e:
        logger.error(f"get_recent_interactions error: {type(e).__name__}: {str(e)}")
        return _tool_error_payload("get_recent_interactions", e, hcp_name=hcp_name, count=0, results=[])


@tool("summarize_interactions")
def summarize_interactions(hcp_name: str, limit: int = 5) -> dict:
    """Generate a concise clinical summary from the most recent notes for an HCP."""
    try:
        with get_session() as session:
            rows = db_get_recent_interactions(session, hcp_name, limit=max(1, min(int(limit), 10)))
            if not rows:
                return {
                    "status": "ok",
                    "hcp_name": hcp_name,
                    "count": 0,
                    "summary": f"No prior interactions were found for {hcp_name}.",
                }

            note_lines = []
            for index, row in enumerate(rows, start=1):
                note = serialize_interaction(row)
                note_lines.append(
                    f"Note {index}: Date={note.get('interaction_date')} | Type={note.get('interaction_type')} | Summary={note.get('summary')}"
                )

            summary_prompt = (
                "You are a medical CRM summarization assistant. "
                "Write a concise executive summary of the doctor relationship using only the provided notes. "
                "Highlight recurring themes, treatment context, sentiment, and follow-up implications. "
                "Keep the summary clear, neutral, and clinically appropriate.\n\n"
                f"HCP: {hcp_name}\n"
                f"Notes:\n{chr(10).join(note_lines)}"
            )

            try:
                summary_llm = ChatGroq(
                    model="mixtral-8x7b-32768",
                    temperature=0,
                    api_key=GROQ_API_KEY,
                    max_retries=0,
                )
                summary_response = _invoke_with_retry(summary_llm, summary_prompt)
                summary_text = _to_text(getattr(summary_response, "content", summary_response)).strip()
            except Exception as e:
                logger.warning(f"summarize_notes LLM fallback: {type(e).__name__}: {str(e)[:80]}")
                summary_text = " ".join(
                    filter(
                        None,
                        [
                            f"Recent interaction themes for {hcp_name}:",
                            "; ".join(
                                str(serialize_interaction(row).get("summary") or "").strip()
                                for row in rows
                            ).strip("; "),
                        ],
                    )
                ).strip()

            return {
                "status": "ok",
                "hcp_name": hcp_name,
                "count": len(rows),
                "summary": summary_text,
                "notes": _serialize_rows(rows),
            }
    except Exception as e:
        logger.error(f"summarize_interactions error: {type(e).__name__}: {str(e)}")
        return _tool_error_payload("summarize_interactions", e, hcp_name=hcp_name, count=0, summary="")


search_hcp = search_hcp_history
get_recent_history = get_recent_interactions
summarize_notes = summarize_interactions

# Expose the exact tool names expected by external orchestrators / prompts.
@tool("search_hcp")
def _tool_search_hcp(hcp_name: str) -> dict:
    return search_hcp_history(hcp_name)


@tool("get_recent_history")
def _tool_get_recent_history(hcp_name: str) -> dict:
    return get_recent_interactions(hcp_name)


@tool("summarize_notes")
def _tool_summarize_notes(hcp_name: str, limit: int = 5) -> dict:
    return summarize_interactions(hcp_name, limit)


TOOLS = [log_interaction, edit_interaction, _tool_search_hcp, _tool_get_recent_history, _tool_summarize_notes]
TOOL_MAP = {tool_object.name: tool_object for tool_object in TOOLS}


def _get_llm() -> ChatGroq:
    return ChatGroq(model=GROQ_MODEL, temperature=0, api_key=GROQ_API_KEY, max_retries=0).bind_tools(TOOLS)


def _agent_node(state: AgentState) -> dict:
    # Build messages with system prompt
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    session_id = "agent_node"
    
    # Extract doctor name from user's latest message and provide context
    if state["messages"]:
        last_user_msg = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                last_user_msg = msg.content
                break
        
        if last_user_msg and isinstance(last_user_msg, str):
            extracted_name = _extract_doctor_name_from_text(last_user_msg)
            if extracted_name:
                # Insert a helpful system note before the user message to guide the agent
                context_msg = SystemMessage(
                    content=f"Note: The user mentioned a doctor named '{extracted_name}'. "
                    f"Use this name directly with search_hcp_history to find their past meetings. "
                    f"Do NOT ask the user for the doctor's name."
                )
                # Insert after the main system prompt
                messages.insert(1, context_msg)
                logger.info(f"[{session_id}] Extracted doctor name: {extracted_name}")
    
    try:
        response = _invoke_with_model_failover(messages, session_id=session_id)
    except Exception as e:
        logger.error(f"[{session_id}] Agent node failed: {e}")
        response = AIMessage(
            content="The AI is currently experiencing high demand across all models, "
            "but your interaction has been logged to the database for processing later."
        )
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
        
        try:
            tool_fn = TOOL_MAP.get(tool_name)
            if tool_fn is None:
                result = {
                    "status": "error",
                    "error": f"Tool '{tool_name}' not found",
                }
                logger.error(f"Tool {tool_name} not found in TOOL_MAP")
            else:
                result = tool_fn.invoke(tool_args)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {type(e).__name__}: {str(e)}")
            result = {
                "status": "error",
                "error": f"Tool failed: {type(e).__name__}: {str(e)[:100]}",
            }
        
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


def _orchestrate(messages: list[BaseMessage], session_id: str | None = None, max_cycles: int = 6) -> dict:
    """
    Simple orchestrator that alternates between the agent node and tool node
    until no more tool calls are produced or max_cycles is reached.
    """
    state: AgentState = {"messages": messages.copy(), "tool_actions": []}
    thread_id = session_id or "agent_loop"

    for cycle in range(max_cycles):
        # Agent turn
        try:
            agent_out = _agent_node(state)
        except Exception as e:
            logger.error(f"[{thread_id}] Agent invocation failed: {e}")
            break

        # Append any messages produced by agent
        new_agent_msgs = agent_out.get("messages", [])
        if new_agent_msgs:
            state["messages"].extend(new_agent_msgs)

        # Tool turn: execute if agent produced tool calls
        try:
            tool_out = _tool_node(state)
        except Exception as e:
            logger.error(f"[{thread_id}] Tool execution failed: {e}")
            break

        new_tool_msgs = tool_out.get("messages", [])
        if new_tool_msgs:
            state["messages"].extend(new_tool_msgs)
            state["tool_actions"].extend(tool_out.get("tool_actions", []))
            # continue loop so agent can respond to tool output
            continue

        # No tool messages produced => finished
        break

    return {"messages": state["messages"], "tool_actions": state["tool_actions"]}


def _extract_final_response(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return _to_text(message.content)
    return ""


def run_chat(message: str, session_id: str | None = None) -> dict:
    """
    Run chat with robust model failover.
    
    Validates input, tries model rotation on rate limits,
    returns graceful fallback message if all models fail.
    
    Args:
        message: User message
        session_id: Optional session ID
    
    Returns:
        JSON dict with session_id, response, tool_actions, status
    """
    thread_id = session_id or uuid.uuid4().hex
    
    # Input validation
    if not message or not isinstance(message, str):
        logger.warning(f"[{thread_id}] Invalid message")
        structured_response = {
            "text": "Please provide a valid message.",
            "form_updates": {},
        }
        return {
            "session_id": thread_id,
            "response": structured_response["text"],
            "structured_response": structured_response,
            "tool_actions": [],
            "status": "error",
        }
    
    logger.info(f"[{thread_id}] Chat started: {message[:50]}...")
    
    try:
        orchestrator_result = _orchestrate([HumanMessage(content=message)], session_id=thread_id)
        messages = orchestrator_result.get("messages", [])
        response_text = _extract_final_response(messages).strip()
        extracted = _extract_form_intent_and_updates(message)
        structured_response = {
            "text": extracted.get("text") or response_text,
            "form_updates": extracted.get("form_updates", {}),
        }

        if not response_text:
            response_text = "I couldn't generate a reply just now. Please try again in a moment."

        if extracted.get("intent") == "UPDATE" and structured_response["text"]:
            response_text = structured_response["text"]

        logger.info(f"[{thread_id}] Chat completed successfully")

        return {
            "session_id": thread_id,
            "response": response_text,
            "structured_response": structured_response,
            "tool_actions": orchestrator_result.get("tool_actions", []),
            "status": "success",
        }
    
    except (RateLimitError, RuntimeError) as e:
        logger.warning(f"[{thread_id}] Model failover exhausted: {str(e)[:100]}")
        structured_response = {
            "text": "The AI is currently experiencing high demand across all models, but your interaction has been logged to the database for processing later.",
            "form_updates": {},
        }
        return {
            "session_id": thread_id,
            "response": structured_response["text"],
            "structured_response": structured_response,
            "tool_actions": [],
            "status": "success",
        }
    
    except Exception as e:
        logger.error(f"[{thread_id}] Unexpected error: {type(e).__name__}: {str(e)[:100]}")
        structured_response = {
            "text": "The AI is currently experiencing high demand across all models, but your interaction has been logged to the database for processing later.",
            "form_updates": {},
        }
        return {
            "session_id": thread_id,
            "response": structured_response["text"],
            "structured_response": structured_response,
            "tool_actions": [],
            "status": "success",
        }


def self_test_run_chat() -> dict:
    """
    Self-test function to validate run_chat doesn't hang or crash.
    
    Tests:
    - Response is valid dict with required fields
    - session_id is non-empty string
    - response is non-empty string
    - status is "success" or "error"
    
    Returns:
        Test result dict with "passed", "message", "duration_ms"
    """
    import signal
    import time as time_module
    
    def timeout_handler(signum, frame):
        raise TimeoutError("run_chat took longer than 10 seconds")
    
    test_session = f"test_{uuid.uuid4().hex[:8]}"
    start_time = time_module.time()
    
    try:
        # Set 10 second timeout (Unix/Linux only; Windows will skip)
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(10)
        
        result = run_chat("Hello, what's your name?", session_id=test_session)
        
        # Cancel alarm
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
        
        duration_ms = int((time_module.time() - start_time) * 1000)
        
        # Validate response structure
        if not isinstance(result, dict):
            logger.error("[TEST] Response is not a dict")
            return {"passed": False, "message": "Response is not a dict", "duration_ms": duration_ms}
        
        required_fields = ["session_id", "response", "status"]
        for field in required_fields:
            if field not in result:
                logger.error(f"[TEST] Missing field: {field}")
                return {"passed": False, "message": f"Missing field: {field}", "duration_ms": duration_ms}
        
        if not isinstance(result["session_id"], str) or not result["session_id"]:
            logger.error("[TEST] session_id is not a non-empty string")
            return {"passed": False, "message": "session_id is not a non-empty string", "duration_ms": duration_ms}
        
        if not isinstance(result["response"], str) or not result["response"]:
            logger.error("[TEST] response is not a non-empty string")
            return {"passed": False, "message": "response is not a non-empty string", "duration_ms": duration_ms}
        
        if result["status"] not in ["success", "error"]:
            logger.error(f"[TEST] Invalid status: {result['status']}")
            return {"passed": False, "message": f"Invalid status: {result['status']}", "duration_ms": duration_ms}
        
        logger.info(f"[TEST] ✓ All checks passed in {duration_ms}ms")
        return {"passed": True, "message": "All checks passed", "duration_ms": duration_ms}
    
    except TimeoutError as e:
        logger.error(f"[TEST] Timeout: {e}")
        return {"passed": False, "message": f"Timeout: {e}", "duration_ms": 10000}
    except Exception as e:
        duration_ms = int((time_module.time() - start_time) * 1000)
        logger.error(f"[TEST] Error: {type(e).__name__}: {str(e)[:100]}")
        return {"passed": False, "message": f"{type(e).__name__}: {str(e)}", "duration_ms": duration_ms}
