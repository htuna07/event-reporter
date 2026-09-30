import importlib
import inspect
import pkgutil
from collections.abc import Mapping

import activity_reporter.sources as sources_package
from activity_reporter.logging import get_logger
from activity_reporter.sources.base import EventSource

logger = get_logger(__name__)


def discover_sources(environment: Mapping[str, str]) -> list[EventSource]:
    prefix = f"{sources_package.__name__}."
    for module in pkgutil.iter_modules(sources_package.__path__, prefix):
        if module.name.rsplit(".", 1)[-1] not in {"base", "discovery"}:
            importlib.import_module(module.name)
            logger.debug("sources.module_discovered", module=module.name)

    configured: list[EventSource] = []
    names: set[str] = set()
    for source_type in _concrete_subclasses(EventSource):
        source = source_type.from_environment(environment)
        if source is None:
            logger.debug("sources.source_not_configured", source_type=source_type.__name__)
            continue
        if source.name in names:
            raise ValueError(
                f"More than one event source uses the name {source.name!r}."
            )
        names.add(source.name)
        configured.append(source)
    discovered = sorted(configured, key=lambda source: source.name)
    logger.log(
        "sources.discovery_completed",
        source_count=len(discovered),
        sources=[source.name for source in discovered],
    )
    return discovered


def _concrete_subclasses(base: type[EventSource]) -> set[type[EventSource]]:
    found: set[type[EventSource]] = set()
    for subclass in base.__subclasses__():
        if not inspect.isabstract(subclass):
            found.add(subclass)
        found.update(_concrete_subclasses(subclass))
    return found
