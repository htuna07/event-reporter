import argparse

from activity_reporter.config import (
    DatabaseSettings,
    IngestionSettings,
    ReportSettings,
    environment,
)
from activity_reporter.database import build_repository
from activity_reporter.ingestion import IngestionService
from activity_reporter.logging import configure_logging, get_logger
from activity_reporter.reporting import ReportService
from activity_reporter.reporters import build_report_generator
from activity_reporter.sources.discovery import discover_sources

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="activity-reporter")
    parser.add_argument("command", choices=("ingest", "report"))
    parser.add_argument(
        "--debug",
        action="store_true",
        help="emit diagnostic log messages",
    )
    parser.add_argument(
        "--log-output",
        default="stdout",
        metavar="stdout|PATH",
        help="write logs to stdout or append them to PATH (default: stdout)",
    )
    parser.add_argument(
        "--log-format",
        choices=("text", "json"),
        default="text",
        help="render logs as text or JSON (default: text)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        configure_logging(
            debug=arguments.debug,
            output=arguments.log_output,
            log_format=arguments.log_format,
        )
    except (OSError, ValueError) as error:
        parser.error(f"Unable to configure logging: {type(error).__name__}")

    logger.log(
        "command.started",
        command=arguments.command,
        log_output=arguments.log_output,
        log_format=arguments.log_format,
    )
    try:
        values = environment()
        repository = build_repository(
            DatabaseSettings.from_environment(values).url)
    except Exception as error:
        logger.error("command.initialization_failed", error_type=type(error).__name__)
        return 1

    if arguments.command == "ingest":
        try:
            repository.create_schema()
            logger.log("database.schema_ready")
            settings = IngestionSettings.from_environment(values)
            sources = discover_sources(values)
        except Exception as error:
            logger.error("ingestion.initialization_failed", error_type=type(error).__name__)
            return 1
        if not sources:
            logger.error("ingestion.no_sources_configured")
            return 1
        logger.log(
            "ingestion.sources_configured",
            source_count=len(sources),
            sources=[source.name for source in sources],
            start=settings.start.isoformat(),
            end=settings.end.isoformat(),
        )
        service = IngestionService(repository)
        result: dict[str, int] = {}
        for source in sources:
            logger.log("ingestion.source_started", source=source.name)
            try:
                result[source.name] = service.ingest(
                    source,
                    settings.start,
                    settings.end,
                )
            except Exception as error:
                logger.error(
                    "ingestion.source_failed",
                    source=source.name,
                    error_type=type(error).__name__,
                )
                return 1
            logger.log(
                "ingestion.source_completed",
                source=source.name,
                processed_events=result[source.name],
            )
        logger.log("ingestion.completed", sources=result)
        return 0

    try:
        settings = ReportSettings.from_environment(values)
        generator = build_report_generator(settings)
        logger.log(
            "report.started",
            provider=settings.provider,
            model=settings.model,
            actor_count=len(settings.actors),
            start=settings.start.isoformat(),
            end=settings.end.isoformat(),
        )
        report = ReportService(repository, generator).create(
            settings.actors,
            settings.start,
            settings.end,
        )
    except Exception as error:
        logger.error("report.generation_failed", error_type=type(error).__name__)
        return 1

    try:
        settings.output_path.parent.mkdir(parents=True, exist_ok=True)
        settings.output_path.write_text(report, encoding="utf-8")
    except OSError as error:
        logger.error("report.output_write_failed", error_type=type(error).__name__)
        return 1
    print(report)
    logger.log(
        "report.completed",
        output_path=str(settings.output_path),
        output_characters=len(report),
    )
    return 0
