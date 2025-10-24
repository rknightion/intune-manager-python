from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QCoreApplication, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from intune_manager.utils import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class TranslationLoadResult:
    locale: str
    loaded: bool
    path: Path | None
    fallback_used: bool


class TranslationManager:
    """Manage Qt translation catalogs for the UI shell."""

    def __init__(
        self,
        app: QApplication,
        *,
        translations_dir: Path | None = None,
        domain: str = "intune_manager",
        fallback_locale: str = "en",
    ) -> None:
        self._app = app
        self._domain = domain
        self._fallback = fallback_locale
        self._translations_dir = translations_dir or (
            Path(__file__).resolve().parent.parent / "translations"
        )
        self._translator = QTranslator(app)
        self._installed_locale: str | None = None

    # ----------------------------------------------------------------- Lifecycle

    def load(self, locale: str | None = None) -> TranslationLoadResult:
        system_locale = locale or QLocale.system().name()
        candidates = list(self._candidate_locales(system_locale))
        logger.debug(
            "Attempting translation load",
            locale=system_locale,
            candidates=candidates,
            directory=str(self._translations_dir),
        )

        for candidate in candidates:
            if self._try_install(candidate):
                logger.info("Loaded translation", locale=candidate)
                return TranslationLoadResult(
                    locale=candidate,
                    loaded=True,
                    path=self._resolved_path(candidate),
                    fallback_used=candidate != system_locale,
                )

        logger.debug(
            "No translation catalog found; continuing with default strings",
            requested=system_locale,
            fallback=self._fallback,
        )
        self._installed_locale = None
        return TranslationLoadResult(
            locale=self._fallback,
            loaded=False,
            path=None,
            fallback_used=True,
        )

    def available_locales(self) -> list[str]:
        if not self._translations_dir.exists():
            return []
        locales: set[str] = set()
        for path in self._translations_dir.glob(f"{self._domain}_*.qm"):
            suffix = path.stem.removeprefix(f"{self._domain}_")
            locales.add(suffix)
        return sorted(locales)

    # ----------------------------------------------------------------- Helpers

    def _candidate_locales(self, locale: str) -> Iterable[str]:
        normalised = locale.replace("-", "_")
        yield normalised
        base = normalised.split("_", 1)[0]
        if base != normalised:
            yield base
        if self._fallback not in {normalised, base}:
            yield self._fallback

    def _resolved_path(self, locale: str) -> Path:
        return self._translations_dir / f"{self._domain}_{locale}.qm"

    def _try_install(self, locale: str) -> bool:
        path = self._resolved_path(locale)
        if not path.exists():
            return False

        logger.debug("Installing translation catalog", locale=locale, path=str(path))
        if self._installed_locale:
            QCoreApplication.removeTranslator(self._translator)
            self._translator = QTranslator(self._app)

        if not self._translator.load(path):
            logger.warning("Failed to load translation file", path=str(path))
            return False

        QCoreApplication.installTranslator(self._translator)
        self._installed_locale = locale
        return True


__all__ = ["TranslationManager", "TranslationLoadResult"]
