# Activity Reporter

Activity Reporter has two independent workflows:

1. `ingest` discovers configured event sources, fetches raw events, converts them to a common format, and stores them in PostgreSQL.
2. `report` queries stored events by an exact actor list and time range, then asks Anthropic to write a report.

The application loads `.env` from the project directory. Variables already exported in the process environment take precedence.

## Common event format

Every adapter produces:

```text
id
external_id
source
timestamp
actor
action
resource
```

PostgreSQL also retains `raw_payload` as JSONB. `id` is a PostgreSQL-generated identity. Adapters provide `external_id`, which contains the source-native event ID. A unique `(source, external_id)` constraint makes repeated ingestion idempotent while allowing different sources to use the same external ID. Timestamps are stored in UTC. Ranges include the start and exclude the end.

### GitHub mapping

- `external_id`: `id`
- `source`: `github`
- `timestamp`: `created_at`
- `actor`: `actor.login`
- `action`: event type plus its meaningful action, such as `pull_request.merged`, `pull_request_review.approved`, or `push`
- `resource`: pull request or issue URL and title when available; otherwise repository and ref, or repository name

### CloudTrail mapping

- `external_id`: `EventId`, falling back to `CloudTrailEvent.eventID`
- `source`: `aws_cloudtrail`
- `timestamp`: `EventTime`, falling back to `CloudTrailEvent.eventTime`
- `actor`: `Username`, then the nested user name, ARN, or principal ID
- `action`: `EventName`
- `resource`: CloudTrail resource names, selected request resource identifiers, or the AWS service and region

## Installation

Python 3.10 or newer and PostgreSQL are required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

### Local PostgreSQL

Start the development database and export its connection URL into your current shell:

```bash
source scripts/start_postgres.sh
```

The script starts or reuses a persistent `activity-reporter-postgres` container, waits until PostgreSQL is ready, and exports `DATABASE_URL`. It binds to `127.0.0.1:55432` by default. To use another host port:

```bash
POSTGRES_PORT=5432 source scripts/start_postgres.sh
```

The database data is retained in the `activity-reporter-postgres-data` Docker volume.

### Application settings

Example `.env` contents:

```dotenv
DATABASE_URL=postgresql+psycopg://activity_reporter:activity_reporter@127.0.0.1:55432/activity_reporter

INGEST_START_TIME=2026-09-25T00:00:00Z
INGEST_END_TIME=2026-09-26T00:00:00Z

GITHUB_REPOSITORIES=Teknodev/spica-hq,spica-engine/spica
GITHUB_TOKEN=github_token

AWS_REGIONS=eu-central-1,us-east-1
AWS_ACTORS=Tuna
AWS_ACCESS_KEY_ID=aws_access_key
AWS_SECRET_ACCESS_KEY=aws_secret_key
AWS_SESSION_TOKEN=optional_session_token

REPORT_ACTORS=htuna07,Tuna
REPORT_START_TIME=2026-09-25T00:00:00Z
REPORT_END_TIME=2026-09-26T00:00:00Z
ANTHROPIC_API_KEY=anthropic_key
ANTHROPIC_MODEL=your_anthropic_model
REPORT_MAX_EVENTS=1000
REPORT_MAX_INPUT_CHARACTERS=200000
REPORT_OUTPUT_PATH=output/report.txt
```

`GITHUB_TOKEN` is optional for public repositories. `AWS_*` credentials use boto3's standard credential chain, so explicit keys are optional. A source is enabled when `GITHUB_REPOSITORIES` or `AWS_REGIONS` is set. CloudTrail ingestion requires `AWS_ACTORS` and applies an exact AWS `Username` filter before storing events. The legacy singular `AWS_ACTOR_USERNAME` setting is also accepted.

Reports are written to `output/reports/activity-report.md` by default. Set `REPORT_OUTPUT_PATH` to use another location. The report is also printed to stdout.

Report generation rejects inputs above `REPORT_MAX_EVENTS` or `REPORT_MAX_INPUT_CHARACTERS` before making an Anthropic request. Narrow the report range or deliberately raise these limits when a query exceeds them.

Start PostgreSQL if needed, then invoke either workflow:

```bash
source scripts/start_postgres.sh
python -m activity_reporter ingest
python -m activity_reporter report
```

The ingestion command creates the table and index if absent. Alembic is intentionally omitted at this stage; add migrations before evolving a schema that contains data which must be preserved.

`create_all` does not alter an existing `events` table. If the earlier composite-key schema was already created, migrate it or recreate the empty table before running this version.

## Adding a source

Add an adapter under `activity_reporter/adapters/` and an `EventSource` subclass under `activity_reporter/sources/`. Implement `from_environment`, `fetch`, and `adapt`, and give the source a unique name. Source modules are discovered automatically, so shared ingestion, database, query, reporting, and CLI code need no changes.
