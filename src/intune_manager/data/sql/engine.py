from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, MutableMapping

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from intune_manager.config.settings import cache_dir
from intune_manager.utils import get_logger

from .models import SchemaVersion


logger = get_logger(__name__)

SCHEMA_VERSION = (
    4  # Added filter_type field to MobileAppAssignmentRecord for include/exclude mode
)


@dataclass(slots=True)
class DatabaseConfig:
    """Configuration options for the SQLite persistence layer."""

    path: Path = field(default_factory=lambda: cache_dir() / "intune-manager.db")
    echo: bool = False
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"
    connect_args: MutableMapping[str, object] = field(
        default_factory=lambda: {"check_same_thread": False, "timeout": 30},
    )

    def uri(self) -> str:
        return f"sqlite:///{self.path}"

    def ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def busy_timeout_ms(self) -> int:
        timeout = self.connect_args.get("timeout")
        if timeout is None:
            return 0
        try:
            return int(float(timeout) * 1000)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return 0


class DatabaseManager:
    """Creates SQLModel engine/session instances and handles schema versioning."""

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self._config = config or DatabaseConfig()
        self._config.ensure_parent()
        self._engine: Engine | None = None

    # ------------------------------------------------------------------ Engine

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            logger.debug("Creating SQLite engine", path=str(self._config.path))
            self._engine = create_engine(
                self._config.uri(),
                echo=self._config.echo,
                connect_args=dict(self._config.connect_args),
                future=True,
            )
            self._apply_sqlite_pragmas(self._engine)
        return self._engine

    # ---------------------------------------------------------------- Schema

    def ensure_schema(self) -> None:
        """Create schema if missing and validate version."""
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            record = session.get(SchemaVersion, "schema_version")
            if record is None:
                session.add(SchemaVersion(version=SCHEMA_VERSION))
                session.commit()
                logger.info("Initialised database schema", version=SCHEMA_VERSION)
            elif record.version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {record.version} does not match expected {SCHEMA_VERSION}",
                )

    # ------------------------------------------------------------- Sessions

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Context manager yielding a SQLModel session."""
        with Session(self.engine) as session:
            yield session

    # ------------------------------------------------------------ Connection

    def _apply_sqlite_pragmas(self, engine: Engine) -> None:
        """Enable WAL mode and busy timeout on new connections."""

        busy_timeout_ms = self._config.busy_timeout_ms()
        journal_mode = self._config.journal_mode
        synchronous = self._config.synchronous

        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[override]
            if not isinstance(dbapi_connection, sqlite3.Connection):
                return
            cursor = dbapi_connection.cursor()
            if journal_mode:
                cursor.execute(f"PRAGMA journal_mode={journal_mode}")
            if synchronous:
                cursor.execute(f"PRAGMA synchronous={synchronous}")
            if busy_timeout_ms:
                cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
            cursor.close()


__all__ = ["DatabaseManager", "DatabaseConfig", "SCHEMA_VERSION"]
