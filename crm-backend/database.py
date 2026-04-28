from __future__ import annotations

import os
from dotenv import load_dotenv
import sys
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Generator

from sqlalchemy import Date, DateTime, Integer, String, Text, create_engine, func
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


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class HCPInteraction(Base):
    __tablename__ = "hcp_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hcp_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    interaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    interaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
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



def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Generator:
    session = SessionLocal()
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
    interaction_type: str,
    summary: str,
) -> HCPInteraction:
    interaction = HCPInteraction(
        hcp_name=hcp_name.strip(),
        interaction_date=interaction_date,
        interaction_type=interaction_type.strip(),
        summary=summary.strip(),
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