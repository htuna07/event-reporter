import argparse
import json

from activity_reporter.config import (
    DatabaseSettings,
    IngestionSettings,
    ReportSettings,
    environment,
)
from activity_reporter.database import build_repository
from activity_reporter.ingestion import IngestionService
from activity_reporter.reporting import AnthropicReportGenerator, ReportService
from activity_reporter.sources.discovery import discover_sources


def main() -> None:
    parser = argparse.ArgumentParser(prog="activity-reporter")
    parser.add_argument("command", choices=("ingest", "report"))
    arguments = parser.parse_args()
    values = environment()
    repository = build_repository(DatabaseSettings.from_environment(values).url)

    if arguments.command == "ingest":
        repository.create_schema()
        settings = IngestionSettings.from_environment(values)
        sources = discover_sources(values)
        if not sources:
            raise ValueError(
                "No event sources are configured. Set GITHUB_REPOSITORIES and/or "
                "AWS_REGIONS in .env."
            )
        service = IngestionService(repository)
        result = {}
        for source in sources:
            print(f"Ingesting {source.name}...", flush=True)
            result[source.name] = service.ingest(
                source,
                settings.start,
                settings.end,
            )
            print(f"Ingested {result[source.name]} {source.name} events.", flush=True)
        print(json.dumps(result, indent=2))
        return

    settings = ReportSettings.from_environment(values)
    generator = AnthropicReportGenerator(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        max_events=settings.max_events,
        max_input_characters=settings.max_input_characters,
    )
    report = ReportService(repository, generator).create(
        settings.actors,
        settings.start,
        settings.end,
    )
    settings.output_path.parent.mkdir(parents=True, exist_ok=True)
    settings.output_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nReport written to {settings.output_path}")
