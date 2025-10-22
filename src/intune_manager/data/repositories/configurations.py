from __future__ import annotations

from datetime import timedelta

from intune_manager.data.models import ConfigurationProfile
from intune_manager.data.sql import ConfigurationProfileRecord
from intune_manager.data.sql.mapper import (
    configuration_to_record,
    record_to_configuration,
)

from .base import BaseCacheRepository


class ConfigurationProfileRepository(
    BaseCacheRepository[ConfigurationProfile, ConfigurationProfileRecord],
):
    def __init__(self, db) -> None:
        super().__init__(
            db,
            resource_name="configuration_profiles",
            record_model=ConfigurationProfileRecord,
            default_ttl=timedelta(minutes=30),
        )

    def _to_record(
        self,
        model: ConfigurationProfile,
        tenant_id: str | None,
    ) -> ConfigurationProfileRecord:
        return configuration_to_record(model, tenant_id=tenant_id)

    def _from_record(self, record: ConfigurationProfileRecord) -> ConfigurationProfile:
        return record_to_configuration(record)


__all__ = ["ConfigurationProfileRepository"]
