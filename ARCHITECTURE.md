# Activity Reporter Architecture

## High-level structure

```text
Environment variables
        │
        ▼
       CLI
    ┌───┴────┐
    ▼        ▼
 Ingestion  Reporting
    │          │
    ▼          ▼
 Sources    PostgreSQL or SQLite query
    │          │
    ▼          ▼
 Adapters    Anthropic or OpenAI
    │          │
    ▼          ▼
 PostgreSQL or SQLite  Text report
                          │
                          ▼
                 Telegram (scripts/)
```

In production the local workflow (`scripts/run_daily_workflow.py`, run by cron
inside Docker) has two modes against a persistent SQLite database: an hourly
`ingest` of the last 2 hours, and a 17:45 `report` that ingests the current
calendar day, reports 00:00 to now, and delivers the report to Telegram.

## Entry points

### `main.py`

Compatibility entry point.

- Imports and calls `activity_reporter.cli.main`.
- Supports `python main.py ingest` and `python main.py report`.
- Both entry points accept the logging options `--debug`, `--log-format`, and `--log-output`.

### `activity_reporter/__main__.py`

Package entry point.

- Supports `python -m activity_reporter ingest` and `python -m activity_reporter report`.
- Delegates execution to the CLI.

### `activity_reporter/__init__.py`

Marks `activity_reporter` as a Python package. It contains no application logic.

## Configuration

### `activity_reporter/config.py`

Loads `.env`, then reads and validates configuration from process environment variables. Variables already exported by the shell take precedence.

- `parse_datetime`: Parses an ISO timestamp, requires a timezone, and converts it to UTC.
- `require`: Reads a required environment variable.
- `comma_separated`: Converts comma-separated configuration into a tuple.
- `DatabaseSettings.from_environment`: Reads `DATABASE_URL`.
- `IngestionSettings.from_environment`: Reads and validates the ingestion time range.
- `ReportSettings.from_environment`: Reads actors, report range, selected report-provider settings, input limits, and the output path. `REPORT_PROVIDER` defaults to `openai` and `OPENAI_MODEL` to `gpt-6-luna`; Anthropic has no default model. The defaults live only in `config.py`.
- `environment`: Loads `.env` without overriding exported values, then returns the process environment.

## Domain models

### `activity_reporter/domain.py`

Defines the common event representations used throughout the application.

#### `NormalizedEvent`

Produced by adapters before database insertion.

```text
external_id
source
timestamp
actor
action
resource
raw_payload
```

- `__post_init__`: Validates required fields and converts the timestamp to UTC.

#### `StoredEvent`

Represents an event read from PostgreSQL. It extends `NormalizedEvent` with the internal, database-generated `id`.

- `common_fields`: Returns the normalized fields sent to the LLM, excluding the raw payload.

## Adapters

Adapters only convert source-specific payloads into `NormalizedEvent` objects.

### `activity_reporter/adapters/base.py`

Defines the adapter contract.

- `EventAdapter.adapt`: Every adapter must implement this conversion method.
- `json_safe`: Converts values such as datetimes into JSON-compatible values for `raw_payload`.

### `activity_reporter/adapters/github.py`

Converts GitHub events into the common format.

- `GitHubAdapter.adapt`: Maps a GitHub payload to `NormalizedEvent`.
- `_action`: Produces actions such as `push`, `pull_request.merged`, or `pull_request_review.approved`.
- `_resource`: Identifies the repository, branch, issue, or pull request.
- `_numbered_resource`: Formats issue and pull-request resources.
- `_required_string`: Reads a required GitHub field.
- `_nested_string`: Safely reads a nested field.
- `_snake_case`: Normalizes GitHub event type names.

### `activity_reporter/adapters/cloudtrail.py`

Converts AWS CloudTrail events into the common format.

- `CloudTrailAdapter.adapt`: Maps a CloudTrail payload to `NormalizedEvent`.
- `_detail`: Parses the nested `CloudTrailEvent` JSON.
- `_timestamp`: Normalizes an AWS timestamp.
- `_resource`: Finds an AWS resource name, ARN, or service identifier.
- `_nested`: Safely reads a nested field.
- `_first`: Selects the first available fallback value.

## Source clients

Sources fetch raw events. They do not decide how events are stored or reported.

### `activity_reporter/sources/base.py`

Defines the source contract.

- `from_environment`: Creates a source when its configuration is present.
- `fetch`: Retrieves raw events for a time range.
- `adapter`: Identifies the adapter that handles the source payloads.

### `activity_reporter/sources/github.py`

Fetches repository events from GitHub.

- `Repository`: Holds a repository owner and name.
- `GitHubSource.__init__`: Configures repositories, authentication, HTTP session, and adapter.
- `from_environment`: Reads `GITHUB_REPOSITORIES` and `GITHUB_TOKEN`.
- `fetch`: Fetches events from every configured repository.
- `_fetch_repository`: Handles pagination and time filtering for one repository.
- `_repository`: Parses an `owner/repository` configuration value.

### `activity_reporter/sources/cloudtrail.py`

Fetches events from AWS CloudTrail.

- `CloudTrailSource.__init__`: Configures AWS regions, boto3 session, and adapter.
- `from_environment`: Enables the source when `AWS_REGIONS` is configured and reads exact actors from `AWS_ACTORS` or the legacy `AWS_ACTOR_USERNAME`.
- `fetch`: Uses the CloudTrail paginator and AWS `Username` lookup filter for each configured region and actor.

### `activity_reporter/sources/discovery.py`

Automatically discovers source implementations.

- `discover_sources`: Imports source modules and returns the configured implementations.
- `_concrete_subclasses`: Finds usable `EventSource` subclasses.

Shared ingestion code does not need to change when a new source is added.

## Database

### `activity_reporter/database.py`

Contains the PostgreSQL and SQLite schema and database operations.

#### `EventRow`

Defines the SQLAlchemy table:

- `id` is generated by the selected database.
- `(source, external_id)` is unique and prevents duplicate ingestion.
- `(actor, timestamp)` is indexed for report queries.
- `raw_payload` and `attributes` use JSON, with JSONB on PostgreSQL.
- Event timestamps are normalized to UTC; SQLite results are restored as
  timezone-aware UTC datetimes.

#### `EventRepository`

- `create_schema`: Creates the table and indexes when they do not exist.
- `upsert`: Inserts events or updates matching `(source, external_id)` records.
- `find`: Returns events matching any supplied actor within the requested time range.

#### `build_repository`

Creates the SQLAlchemy engine and repository from `DATABASE_URL`. PostgreSQL
and SQLite URL schemes are supported. Parent directories for file-backed
SQLite databases are created when needed. SQLite connections wait up to 30
seconds for a concurrent writer (`busy_timeout`) before failing.

## Application services

### `activity_reporter/ingestion.py`

Coordinates ingestion without depending on a particular event source.

#### `IngestionService`

- `__init__`: Receives an event writer and batch size.
- `ingest`: Fetches raw payloads, adapts them, stores them in batches, and returns the processed count.

### `activity_reporter/reporting.py` and `activity_reporter/reporters/`

Coordinates database querying and report generation.

#### `ReportGenerator`

Defines the interface implemented by an LLM report generator.

#### Report generator strategies

- `reporting.py` contains `ReportService`, which remains unaware of the selected provider.
- `reporters/factory.py` selects OpenAI (default) or Anthropic from `REPORT_PROVIDER`.
- `reporters/base.py` also holds the shared `REPORT_INSTRUCTIONS` prompt and orders events so failed, write, and collaboration activity precede read-only activity.
- `reporters/base.py` validates and serializes report inputs once for every provider; each provider implementation owns only its SDK call.

#### Adding a provider

Add a generator under `activity_reporter/reporters/` that subclasses `BaseReportGenerator` and implements `_generate`, register it in `reporters/factory.py`, and add its settings to `ReportSettings.from_environment`.

#### `ReportService`

- `__init__`: Receives an event reader and report generator.
- `create`: Queries stored events and passes them to the report generator.

### `activity_reporter/redaction.py`

Removes credential-like values and GitHub free-text bodies from raw payloads before they are persisted.

### `activity_reporter/logging.py`

Configurable structured logging (text or JSON Lines, stdout or file). Entries never include credentials, connection URLs, headers, raw payloads, or report prompts.

## Interfaces

### `activity_reporter/ports.py`

Defines the boundaries between application services and storage.

- `EventWriter.upsert`: Required by ingestion.
- `EventReader.find`: Required by reporting.

These interfaces keep services independent from SQLAlchemy and make testing easier.

## CLI orchestration

### `activity_reporter/cli.py`

Connects configuration, sources, adapters, storage, and reporting.

#### `main`

For `ingest`:

```text
Read configuration
    → connect to PostgreSQL or SQLite
    → create schema
    → discover configured sources
    → fetch and adapt events
    → store events
```

For `report`:

```text
Read configuration
    → connect to PostgreSQL or SQLite
    → query actors and time range
    → generate a report through the selected provider
    → print report
    → optionally write report to a file
```

## Scripts

- `scripts/run_daily_workflow.py`: `--mode ingest` stores the last 2 hours (overlapping windows, idempotent upserts) and notifies Telegram only after three consecutive failures. `--mode report` ingests the Europe/Istanbul calendar day so far, generates the report, appends a plain-text data notice when some sources failed to refresh (exit status 2 from `ingest`, details from `--failures-output`), and delivers it to Telegram. Both use the SQLite database on the output volume, do not lock against each other, enforce a 30-minute timeout, and report failures notify Telegram with the failed stage.
- `scripts/container_entrypoint.py`: Writes the container environment to a restricted runtime file and starts cron.
- `scripts/send_telegram_report.py`: Reads a plain-text report from stdin and sends it to Telegram, splitting long reports across messages.
- `scripts/redact_raw_payloads.py`: Redacts already-retained payloads.
- `scripts/start_postgres.sh`: Starts a local development PostgreSQL container.

## Deployment

- `Dockerfile`, `compose.yaml`, and `docker/daily-activity-report`: A Compose scheduler with cron firing hourly (ingestion) and at 17:45 Europe/Istanbul (report). Reports and logs persist in the `activity-reporter-output` volume.
- `.github/workflows/daily-activity-report.yml`: Equivalent GitHub Actions workflow, currently disabled with `if: ${{ false }}`.
- `migrations/` and `alembic.ini`: Alembic migrations for existing PostgreSQL or SQLite databases.

## Tests

- `tests/test_github_adapter.py`: Verifies GitHub normalization.
- `tests/test_cloudtrail_adapter.py`: Verifies CloudTrail normalization.
- `tests/test_sources.py`: Verifies pagination and source-fetching behavior.
- `tests/test_discovery.py`: Verifies automatic source discovery.
- `tests/test_config.py`: Verifies configuration parsing and validation.
- `tests/test_services.py`: Verifies ingestion and reporting orchestration.
- `tests/test_database_schema.py`: Verifies the generated identity and unique constraint.
- `tests/test_redaction.py`: Verifies payload redaction.
- `tests/test_logging.py`: Verifies log formats and secret-free output.
- `tests/test_cli.py`: Verifies ingestion continues past failing sources and reports them.
- `tests/test_daily_workflow.py`: Verifies the daily workflow stages, windows, ingestion failure streaks, and failure notification.

Run them with `python -m pytest` (install `pytest` in addition to `requirements.txt`).

## Supporting files

### `requirements.txt`

Lists the runtime dependencies: Anthropic, OpenAI, boto3, psycopg, python-dotenv, requests, SQLAlchemy, and Alembic.

### `README.md`

Documents installation, configuration, commands, field mappings, and adding a new source.

## Complete ingestion flow

```text
GitHub / CloudTrail
        │ raw dictionaries
        ▼
EventSource.fetch
        │
        ▼
EventAdapter.adapt
        │ NormalizedEvent
        ▼
IngestionService
        │ batches
        ▼
EventRepository.upsert
        │
        ▼
PostgreSQL or SQLite
```

## Complete reporting flow

```text
Actors + time range
        │
        ▼
EventRepository.find
        │ StoredEvent list
        ▼
ReportService
        │ common fields only
        ▼
Selected report generator
        │ Anthropic or OpenAI
        │
        ▼
Text report
        │
        ▼
Telegram (daily workflow)
```
