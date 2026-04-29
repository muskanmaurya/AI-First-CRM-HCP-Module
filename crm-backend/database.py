from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from dotenv import load_dotenv
import sys
import logging
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Generator

from sqlalchemy import Date, DateTime, Integer, JSON, String, Text, create_engine, inspect, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # For robustness during deploy or local development when DATABASE_URL
    # isn't provided, fall back to a local SQLite file and log a warning.
    # Production deployments should set DATABASE_URL to a managed Postgres instance.
    print(
        "WARNING: DATABASE_URL not set. Falling back to local SQLite 'dev.db'.",
        file=sys.stderr,
    )
    DATABASE_URL = f"sqlite:///./dev.db"
else:
    # Normalize common Postgres URL forms to the SQLAlchemy dialect that
    # uses psycopg (psycopg3) so SQLAlchemy will import the correct DBAPI.
    # Examples:
    #  - postgres://...        -> postgresql+psycopg://...
    #  - postgresql://...      -> postgresql+psycopg://...
    # If the URL already specifies a dialect like postgresql+psycopg2://,
    # leave it as-is.
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    if DATABASE_URL.startswith("postgresql+psycopg://") and "sslmode=" not in DATABASE_URL:
        parts = urlsplit(DATABASE_URL)
        query_params = dict(parse_qsl(parts.query, keep_blank_values=True))
        query_params["sslmode"] = "require"
        DATABASE_URL = urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(query_params),
                parts.fragment,
            )
        )
    # Log the resolved URL scheme for debugging (do not log credentials)
    logger = logging.getLogger(__name__)
    try:
        scheme = DATABASE_URL.split("://", 1)[0]
        logger.info(f"Using database scheme: {scheme}")
    except Exception:
        pass


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    """Lazy-load SQLAlchemy engine to avoid crashes during import."""
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
    return _engine


def get_session_maker():
    """Lazy-load session maker."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def _build_summary(
    *,
    hcp_name: str,
    interaction_date: date,
    interaction_type: str | None = None,
    time: str | None = None,
    attendees: str | None = None,
    topics: str | None = None,
    materials: list | None = None,
    samples: list | None = None,
    sentiment: str | None = None,
    outcomes: str | None = None,
    follow_up: str | None = None,
) -> str:
    parts = [f"HCP: {hcp_name}", f"Date: {interaction_date.isoformat()}"]
    if interaction_type:
        parts.append(f"Type: {interaction_type}")
    if time:
        parts.append(f"Time: {time}")
    if attendees:
        parts.append(f"Attendees: {attendees}")
    if topics:
        parts.append(f"Topics: {topics}")
    if materials:
        parts.append(f"Materials: {', '.join(map(str, materials))}")
    if samples:
        parts.append(f"Samples: {', '.join(map(str, samples))}")
    if sentiment:
        parts.append(f"Sentiment: {sentiment}")
    if outcomes:
        parts.append(f"Outcomes: {outcomes}")
    if follow_up:
        parts.append(f"Follow-up: {follow_up}")
    return " | ".join(parts)


class HCPInteraction(Base):
    __tablename__ = "hcp_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hcp_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    interaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    interaction_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attendees: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics: Mapped[str | None] = mapped_column(Text, nullable=True)
    materials: Mapped[list | None] = mapped_column(JSON, nullable=True)
    samples: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcomes: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user, assistant, tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )



def _ensure_interaction_columns() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns(HCPInteraction.__tablename__)}

    with engine.begin() as connection:
        for column in HCPInteraction.__table__.columns:
            if column.name == "id" or column.name in existing_columns:
                continue
            compiled_type = column.type.compile(dialect=engine.dialect)
            connection.execute(text(f'ALTER TABLE {HCPInteraction.__tablename__} ADD COLUMN {column.name} {compiled_type}'))


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())
    _ensure_interaction_columns()


@contextmanager
def get_session() -> Generator:
    session = get_session_maker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def serialize_interaction(interaction: HCPInteraction) -> dict:
    return {
        "id": interaction.id,
        "hcp_name": interaction.hcp_name,
        "interaction_date": interaction.interaction_date.isoformat(),
        "interaction_type": interaction.interaction_type,
        "time": interaction.time,
        "attendees": interaction.attendees,
        "topics": interaction.topics,
        "materials": interaction.materials,
        "samples": interaction.samples,
        "sentiment": interaction.sentiment,
        "outcomes": interaction.outcomes,
        "follow_up": interaction.follow_up,
        "summary": interaction.summary,
        "timestamp": interaction.timestamp.isoformat() if interaction.timestamp else None,
    }


def create_chat_session(session, session_id: str, title: str) -> ChatSession:
    sess = ChatSession(id=session_id, title=title)
    session.add(sess)
    session.flush()
    session.refresh(sess)
    return sess


def get_all_sessions(session) -> list[ChatSession]:
    return session.query(ChatSession).order_by(ChatSession.created_at.desc()).all()


def create_chat_message(session, session_id: str, role: str, content: str) -> ChatMessage:
    msg = ChatMessage(session_id=session_id, role=role, content=content)
    session.add(msg)
    session.flush()
    session.refresh(msg)
    return msg


def get_messages_for_session(session, session_id: str) -> list[ChatMessage]:
    return (
        session.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp.asc())
        .all()
    )


def create_interaction(
    session,
    *,
    hcp_name: str,
    interaction_date: date,
    interaction_type: str | None = None,
    time: str | None = None,
    attendees: str | None = None,
    topics: str | None = None,
    materials: list | None = None,
    samples: list | None = None,
    sentiment: str | None = None,
    outcomes: str | None = None,
    follow_up: str | None = None,
    summary: str | None = None,
) -> HCPInteraction:
    derived_summary = summary or _build_summary(
        hcp_name=hcp_name,
        interaction_date=interaction_date,
        interaction_type=interaction_type,
        time=time,
        attendees=attendees,
        topics=topics,
        materials=materials,
        samples=samples,
        sentiment=sentiment,
        outcomes=outcomes,
        follow_up=follow_up,
    )

    interaction = HCPInteraction(
        hcp_name=hcp_name.strip(),
        interaction_date=interaction_date,
        interaction_type=interaction_type.strip() if interaction_type else None,
        time=time.strip() if isinstance(time, str) and time.strip() else time,
        attendees=attendees.strip() if isinstance(attendees, str) and attendees.strip() else attendees,
        topics=topics.strip() if isinstance(topics, str) and topics.strip() else topics,
        materials=materials,
        samples=samples,
        sentiment=sentiment.strip() if isinstance(sentiment, str) and sentiment.strip() else sentiment,
        outcomes=outcomes.strip() if isinstance(outcomes, str) and outcomes.strip() else outcomes,
        follow_up=follow_up.strip() if isinstance(follow_up, str) and follow_up.strip() else follow_up,
        summary=derived_summary.strip() if derived_summary else None,
    )
    session.add(interaction)
    session.flush()
    session.refresh(interaction)
    return interaction


def update_interaction(session, interaction_id: int, updates: dict) -> HCPInteraction | None:
    interaction = session.get(HCPInteraction, interaction_id)
    if interaction is None:
        return None

    if "hcp_name" in updates and updates["hcp_name"] is not None:
        interaction.hcp_name = str(updates["hcp_name"]).strip()
    if "interaction_date" in updates and updates["interaction_date"] is not None:
        interaction.interaction_date = updates["interaction_date"]
    if "interaction_type" in updates and updates["interaction_type"] is not None:
        interaction.interaction_type = str(updates["interaction_type"]).strip()
    if "time" in updates:
        interaction.time = str(updates["time"]).strip() if updates["time"] else None
    if "attendees" in updates:
        interaction.attendees = str(updates["attendees"]).strip() if updates["attendees"] else None
    if "topics" in updates:
        interaction.topics = str(updates["topics"]).strip() if updates["topics"] else None
    if "materials" in updates:
        interaction.materials = updates["materials"]
    if "samples" in updates:
        interaction.samples = updates["samples"]
    if "sentiment" in updates:
        interaction.sentiment = str(updates["sentiment"]).strip() if updates["sentiment"] else None
    if "outcomes" in updates:
        interaction.outcomes = str(updates["outcomes"]).strip() if updates["outcomes"] else None
    if "follow_up" in updates:
        interaction.follow_up = str(updates["follow_up"]).strip() if updates["follow_up"] else None
    if "summary" in updates and updates["summary"] is not None:
        interaction.summary = str(updates["summary"]).strip()

    session.flush()
    session.refresh(interaction)
    return interaction


def get_interaction_by_id(session, interaction_id: int) -> HCPInteraction | None:
    return session.get(HCPInteraction, interaction_id)


def find_interactions_by_hcp(session, hcp_name: str) -> list[HCPInteraction]:
    query = (
        session.query(HCPInteraction)
        .filter(func.lower(HCPInteraction.hcp_name) == hcp_name.lower())
        .order_by(HCPInteraction.timestamp.desc())
    )
    rows = query.all()
    if rows:
        return rows

    return (
        session.query(HCPInteraction)
        .filter(HCPInteraction.hcp_name.ilike(f"%{hcp_name}%"))
        .order_by(HCPInteraction.timestamp.desc())
        .all()
    )


def get_recent_interactions(session, hcp_name: str, limit: int = 5) -> list[HCPInteraction]:
    return (
        session.query(HCPInteraction)
        .filter(func.lower(HCPInteraction.hcp_name) == hcp_name.lower())
        .order_by(HCPInteraction.timestamp.desc())
        .limit(limit)
        .all()
    )


def get_all_interactions(session, hcp_name: str) -> list[HCPInteraction]:
    return (
        session.query(HCPInteraction)
        .filter(func.lower(HCPInteraction.hcp_name) == hcp_name.lower())
        .order_by(HCPInteraction.timestamp.desc())
        .all()
    )


def get_recent_interactions_global(session, limit: int = 10) -> list[HCPInteraction]:
    """Get the most recent N interactions from the database (all HCPs)."""
    return (
        session.query(HCPInteraction)
        .order_by(HCPInteraction.timestamp.desc())
        .limit(limit)
        .all()
    )


def delete_interaction(session, interaction_id: int) -> bool:
    """Delete an interaction by ID. Returns True if deleted, False if not found."""
    interaction = session.get(HCPInteraction, interaction_id)
    if interaction is None:
        return False
    
    session.delete(interaction)
    session.flush()
    return True