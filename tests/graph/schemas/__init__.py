"""Utilities for loading Microsoft Graph OpenAPI schemas in tests."""

from .loader import GraphSchemaRegistry, load_default_registry

__all__ = ["GraphSchemaRegistry", "load_default_registry"]
