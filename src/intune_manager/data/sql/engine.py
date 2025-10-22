from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, MutableMapping

from sqlmodel import Session, SQLModel, create_engine

from intune_manager.config.settings import cache_dir
from intune_manager.utils import get_logger

from .models import SchemaVersion


logger = get_logger(__name__)

SCHEMA_VERSION = 1


@dataclass(slots=True)
class DatabaseConfig:
    """Configuration options for the SQLite persistence layer."""

    path: Path = field(default_factory=lambda: cache_dir() / "intune-manager.db")
    echo: bool = False
    connect_args: MutableMapping[str, object] = field(
        default_factory=lambda: {"check_same_thread": False},
    )

    def uri(self) -> str:
        return f"sqlite:///{self.path}"

    def ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)


class DatabaseManager:
    """Creates SQLModel engine/session instances and handles schema versioning."""

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self._config = config or DatabaseConfig()
        self._config.ensure_parent()
        self._engine = None

    # ------------------------------------------------------------------ Engine

    @property
    def engine(self):
        if self._engine is None:
            logger.debug("Creating SQLite engine", path=str(self._config.path))
            self._engine = create_engine(
                self._config.uri(),
                echo=self._config.echo,
                connect_args=dict(self._config.connect_args),
                future=True,
            )
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


__all__ = ["DatabaseManager", "DatabaseConfig", "SCHEMA_VERSION"]
