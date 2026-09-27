import importlib
import inspect
import pkgutil
from collections.abc import Mapping

import activity_reporter.sources as sources_package
from activity_reporter.sources.base import EventSource


def discover_sources(environment: Mapping[str, str]) -> list[EventSource]:
    prefix = f"{sources_package.__name__}."
    for module in pkgutil.iter_modules(sources_package.__path__, prefix):
        if module.name.rsplit(".", 1)[-1] not in {"base", "discovery"}:
            importlib.import_module(module.name)

    configured: list[EventSource] = []
    names: set[str] = set()
    for source_type in _concrete_subclasses(EventSource):
        source = source_type.from_environment(environment)
        if source is None:
            continue
        if source.name in names:
            raise ValueError(
                f"More than one event source uses the name {source.name!r}."
            )
        names.add(source.name)
        configured.append(source)
    return sorted(configured, key=lambda source: source.name)


def _concrete_subclasses(base: type[EventSource]) -> set[type[EventSource]]:
    found: set[type[EventSource]] = set()
    for subclass in base.__subclasses__():
        if not inspect.isabstract(subclass):
            found.add(subclass)
        found.update(_concrete_subclasses(subclass))
    return found
