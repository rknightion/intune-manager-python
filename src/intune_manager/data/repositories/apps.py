from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Sequence

from sqlalchemy import delete
from sqlmodel import Session, select

from intune_manager.data.models import MobileApp
from intune_manager.data.sql import MobileAppAssignmentRecord, MobileAppRecord
from intune_manager.data.sql.mapper import (
    assignments_to_records,
    mobile_app_to_record,
    record_to_assignment,
    record_to_mobile_app,
)

from .base import BaseCacheRepository


class MobileAppRepository(BaseCacheRepository[MobileApp, MobileAppRecord]):
    def __init__(self, db) -> None:
        super().__init__(
            db,
            resource_name="mobile_apps",
            record_model=MobileAppRecord,
            default_ttl=timedelta(minutes=20),
        )

    def _to_record(self, model: MobileApp, tenant_id: str | None) -> MobileAppRecord:
        return mobile_app_to_record(model, tenant_id=tenant_id)

    def _from_record(self, record: MobileAppRecord) -> MobileApp:
        return record_to_mobile_app(record)

    def _post_replace(
        self,
        session: Session,
        models: Sequence[MobileApp],
        tenant_id: str | None,
    ) -> None:
        assignment_records = []
        for app in models:
            if app.assignments:
                assignment_records.extend(
                    assignments_to_records(
                        app.id, app.assignments, tenant_id=tenant_id
                    ),
                )

        del_stmt = delete(MobileAppAssignmentRecord)
        if tenant_id is not None:
            del_stmt = del_stmt.where(MobileAppAssignmentRecord.tenant_id == tenant_id)
        session.exec(del_stmt)
        for record in assignment_records:
            session.merge(record)

    def list_all(self, *, tenant_id: str | None = None) -> list[MobileApp]:
        with self._db.session() as session:
            records = session.exec(self._select_records(tenant_id)).all()
            app_ids = [record.id for record in records]

            assignments_map: dict[str, list[MobileAppAssignmentRecord]] = defaultdict(
                list
            )
            if app_ids:
                stmt = select(MobileAppAssignmentRecord).where(
                    MobileAppAssignmentRecord.app_id.in_(app_ids),
                )
                if tenant_id is not None:
                    stmt = stmt.where(MobileAppAssignmentRecord.tenant_id == tenant_id)
                assignment_rows = session.exec(stmt).all()
                for row in assignment_rows:
                    assignments_map[row.app_id].append(row)

            apps: list[MobileApp] = []
            for record in records:
                app = self._from_record(record)
                assignments = assignments_map.get(record.id)
                if assignments:
                    app = app.model_copy(
                        update={
                            "assignments": [
                                record_to_assignment(row) for row in assignments
                            ]
                        }
                    )
                apps.append(app)
            return apps


__all__ = ["MobileAppRepository"]
