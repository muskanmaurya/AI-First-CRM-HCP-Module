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
    print(
        "ERROR: DATABASE_URL not set. Please set DATABASE_URL in your .env file.",
        file=sys.stderr,
    )
    raise RuntimeError("DATABASE_URL not set in environment")


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