# Example Activity Report

The following anonymized example is shown with Markdown for readability. Generated reports use plain text.

## Activity Report — September 29, 2026 (Example User / example-user)

### Actions

**Message-consumer resilience feature (`example-org/message-service`)**

- Pushed several commits to `feat/message-consumer-resilience` and commented on PR #123 ("make the message trigger resilient and expose the client API")
- Merged PR #123 and deleted the source branch
- Closed related issue #122 ("acknowledgement methods should be void") with a closing comment

**Code reviews and infrastructure PRs (`example-org`)**

- Approved `cloud-infrastructure` PRs "update application resources" and "adjust network configuration"
- Opened, pushed to `fix/allow-application-hosts`, and merged `cloud-infrastructure` PR "allow application hosts through the firewall"
- Opened and merged `deployment-config` PR "update production deployment" with a push to `main`
- Created branch `example-user-patch-2`, opened `deployment-config` PR "correct service configuration", and later merged it

**AWS message-broker infrastructure migration (`example-region-1`)**

- Extensively explored ECS, EC2, ELB, ACM, and networking resources through the console, CloudShell, and Resource Explorer to assess the existing message-broker setup
- Created a new launch template (`message-broker-template`) and Auto Scaling group (`message-broker-asg`)
- Created an ECS capacity provider, attached it to the message-broker ECS cluster, and then updated the Auto Scaling group
- Deleted five stale test message-broker ECS services
- Created a CloudFormation change set for the message-broker cluster stack to reflect the new capacity-provider setup
- Followed up with monitoring and verification calls for ECS services and tasks, target-group health, and EKS cluster inspection to confirm the migration

### Summary

Example User finalized and merged the message-consumer resilience feature, handled several infrastructure-related reviews and merges across the example organization's repositories, and carried out a significant AWS infrastructure change: replacing the message-broker ECS capacity provider, cleaning up obsolete test services, and updating the CloudFormation stack, followed by verification checks.

---

# Activity Reporter

Activity Reporter has two independent workflows:

1. `ingest` discovers configured event sources, fetches raw events, converts them to a common format, and stores them in PostgreSQL or SQLite.
2. `report` queries stored events by an exact actor list and time range, then asks the selected provider (Anthropic or OpenAI) to write a report.

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

It also records optional structured context when available: event type/action,
activity kind and outcome, service and region, typed resource identifiers,
safe source-specific attributes, correlation identifiers, and a bounded safe
content excerpt. Reports use these fields to prioritize mutations and failures
over read-only activity.

The database retains a redacted `raw_payload` as JSON (JSONB on PostgreSQL).
Credential-like values and GitHub free-text bodies are removed before
persistence. `id` is database-generated. Adapters provide `external_id`, which
contains the source-native event ID. A unique `(source, external_id)` constraint makes
repeated ingestion idempotent while allowing different sources to use the same
external ID. Timestamps are stored in UTC. Ranges include the start and exclude
the end.

### GitHub mapping

- `external_id`: `id`
- `source`: `github`
- `timestamp`: `created_at`
- `actor`: `actor.login`
- `action`: event type plus its meaningful action, such as `pull_request.merged`, `pull_request_review.approved`, or `push`
- `resource`: pull request or issue URL and title when available; otherwise repository and ref, or repository name
- `content_excerpt`: the first 280 characters of a comment or review body, or, for pushes, the commit subjects (first line of each message, at most 500 characters); anything that looks credential-related is skipped

### CloudTrail mapping

- `external_id`: `EventId`, falling back to `CloudTrailEvent.eventID`
- `source`: `aws_cloudtrail`
- `timestamp`: `EventTime`, falling back to `CloudTrailEvent.eventTime`
- `actor`: `Username`, then the nested user name, ARN, or principal ID
- `action`: `EventName`
- `resource`: CloudTrail resource names, selected request resource identifiers, or the AWS service and region

## Installation

Python 3.10 or newer is required. The application supports PostgreSQL and
SQLite.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

### Database selection

Set `DATABASE_URL` to select a database. PostgreSQL remains supported:

```dotenv
DATABASE_URL=postgresql+psycopg://activity_reporter:activity_reporter@127.0.0.1:55432/activity_reporter
```

Use a SQLite file for a local or temporary database:

```dotenv
DATABASE_URL=sqlite:///output/activity-reporter.db
```

The application creates parent directories for file-backed SQLite URLs. A
SQLite file on a GitHub Actions runner does not persist after the job ends.

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

INGEST_START_TIME=2026-01-01T00:00:00Z
INGEST_END_TIME=2026-01-02T00:00:00Z

GITHUB_REPOSITORIES=example-org/web-api,example-org/worker-service
GITHUB_TOKEN=github_token

AWS_REGIONS=eu-central-1,us-east-1
AWS_ACTORS=example-aws-user
AWS_ACCESS_KEY_ID=aws_access_key
AWS_SECRET_ACCESS_KEY=aws_secret_key
AWS_SESSION_TOKEN=optional_session_token

REPORT_ACTORS=example-github-user,example-aws-user
REPORT_START_TIME=2026-01-01T00:00:00Z
REPORT_END_TIME=2026-01-02T00:00:00Z
REPORT_PROVIDER=anthropic
ANTHROPIC_API_KEY=anthropic_key
ANTHROPIC_MODEL=your_anthropic_model
OPENAI_API_KEY=openai_key
OPENAI_MODEL=your_openai_model
REPORT_MAX_EVENTS=1000
REPORT_MAX_INPUT_CHARACTERS=200000
REPORT_MAX_TOKENS=1500
REPORT_OUTPUT_PATH=output/reports/activity-report.txt
```

`GITHUB_TOKEN` is optional for public repositories. `AWS_*` credentials use boto3's standard credential chain, so explicit keys are optional. A source is enabled when `GITHUB_REPOSITORIES` or `AWS_REGIONS` is set. CloudTrail ingestion requires `AWS_ACTORS` and applies an exact AWS `Username` filter before storing events. The legacy singular `AWS_ACTOR_USERNAME` setting is also accepted.

Reports are written to `output/reports/activity-report.txt` by default and are also printed to stdout. Set `REPORT_OUTPUT_PATH` to another location, or set it to an empty value to skip saving the file and print only to stdout.

Running the application directly defaults to Anthropic. The GitHub Actions and Docker workflows default to OpenAI instead, unless `REPORT_PROVIDER` is set. Set `REPORT_PROVIDER=openai` to use OpenAI instead; only the selected provider's API key and model are required. Both providers use the same input limits and report format. Report generation rejects inputs above `REPORT_MAX_EVENTS` or `REPORT_MAX_INPUT_CHARACTERS` before making a provider request. Narrow the report range or deliberately raise these limits when a query exceeds them.

Start PostgreSQL if needed, then invoke either workflow:

```bash
source scripts/start_postgres.sh
python -m activity_reporter ingest
python -m activity_reporter report
```

## Tests

```bash
pip install pytest
python -m pytest
```

## Logging

Operational logs go to stdout as human-readable text by default. Use `--debug`
to include diagnostic messages, `--log-format json` for JSON Lines, and
`--log-output PATH` to append logs to a file instead. The Telegram workflow
stores report-generation logs in `output/logs/activity-reporter.txt` so only the
report text goes through the Telegram pipe:

```bash
python -m activity_reporter ingest --debug --log-format json \
  --log-output logs/activity-reporter.log
```

`--log-output stdout` is the default. Log entries contain the same timestamp,
level, logger name, message, and context fields in both text and JSON formats.
They never include credentials, connection URLs, request headers, raw event
payloads, or report prompts.

The ingestion command creates the table and indexes if absent. For an existing
database, apply schema changes before ingestion. The migrations support both
PostgreSQL and SQLite:

```bash
python -m alembic upgrade head
```

## GitHub Actions and Telegram

`.github/workflows/daily-activity-report.yml` is currently disabled in code:
the `report` job has `if: ${{ false }}` while reports run locally with Docker.
Scheduled and manually dispatched runs skip that job. To re-enable GitHub
reports, remove the condition and push the change; no manual workflow enablement
is required in GitHub.

The workflow retains its daily schedule at 17:45 in `Europe/Istanbul` time
and its `workflow_dispatch` trigger. When enabled, it
ingests and reports the preceding 24 hours using a temporary SQLite database,
then pipes the plain-text report directly to Telegram, splitting long reports
across multiple messages. It also saves the report to
`output/reports/activity-report.txt`. The window is based on the actual workflow
start time.
GitHub may delay scheduled runs during periods of high load.

Configure these repository variables:

- `REPORT_ACTORS`: comma-separated GitHub and/or AWS actor names to include.
- `ACTIVITY_GITHUB_REPOSITORIES`: comma-separated `owner/repository` list
  when using GitHub as a source. The workflow passes it to the application as
  `GITHUB_REPOSITORIES`. Configure either this or CloudTrail as a data source.
- `REPORT_PROVIDER`: optional, `openai` (default) or `anthropic`.
- `OPENAI_MODEL`: optional; defaults to `gpt-6-luna` when using OpenAI.
- `ANTHROPIC_MODEL`: required when `REPORT_PROVIDER=anthropic`.
- `AWS_REGIONS`, `AWS_ACTORS`, `AWS_ROLE_ARN`, and `AWS_DEFAULT_REGION`:
  configure optional CloudTrail ingestion. Leave these unset to skip AWS.
  When enabling it, the AWS role must trust this repository's GitHub Actions
  OIDC identity.

Configure these repository secrets:

- `TELEGRAM_BOT_TOKEN`: token for the Telegram bot that sends the report.
- `OPENAI_API_KEY`: required for the default OpenAI provider.
- `ANTHROPIC_API_KEY`: required when using Anthropic instead.
- `ACTIVITY_GITHUB_TOKEN`: optional token for GitHub repositories the built-in
  workflow token cannot read.

Change the cron expression and `timezone` in the workflow file to change the
scheduled local time or timezone. Set `TELEGRAM_CHAT_ID` as a repository
variable. For a private chat, start the bot in Telegram before its first run.

To redact already-retained payloads and the saved source snapshot without
printing their contents, run:

```bash
python -m scripts.redact_raw_payloads
```

`create_all` does not alter an existing `events` table, so migrations remain
required for existing installations.

## Daily local workflow with Docker

The Docker Compose scheduler runs two cron jobs, both in **Europe/Istanbul** time:

- **Hourly ingestion** (every hour on the hour) re-reads the last 2 hours from
  every configured source and upserts them into a persistent SQLite database.
  The windows deliberately overlap: ingestion is idempotent, and the overlap
  absorbs source delays and missed runs.
- **Daily report** (**17:45**) first ingests the current calendar day, then
  reports every event from **00:00 local time until 17:45** for the configured
  actors and sends the report to Telegram.

Events between 17:45 and midnight are not part of that day's report; they are
stored and fall into no later report window, because each report covers a single
calendar day starting at 00:00. Dependencies are installed when the image is
built. The GitHub Actions workflow is unchanged.

Configure the project's existing `.env` with:

- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- `REPORT_ACTORS` and at least one source: `GITHUB_REPOSITORIES`, or
  `AWS_REGIONS` together with `AWS_ACTORS`.
- `OPENAI_API_KEY` for the default OpenAI provider. `OPENAI_MODEL` defaults to
  `gpt-6-luna`. Alternatively set `REPORT_PROVIDER=anthropic`,
  `ANTHROPIC_API_KEY`, and `ANTHROPIC_MODEL`.
- Optional application limits such as `REPORT_MAX_EVENTS` and
  `REPORT_MAX_INPUT_CHARACTERS`.

Use application setting names locally, such as `GITHUB_REPOSITORIES` and
`GITHUB_TOKEN`, rather than GitHub Actions' `ACTIVITY_GITHUB_*` names. Public
repositories can work without a token; private repositories need a suitable
local token. GitHub Actions' automatic workflow token and AWS OIDC role identity
are not available in this container. If using CloudTrail, supply valid local
AWS credentials through the supported `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, and optional `AWS_SESSION_TOKEN` settings. Expiring AWS
credentials must be refreshed and the container recreated.

Start the scheduler:

```bash
docker compose up -d --build
```

On macOS, enable **Start Docker Desktop when you sign in to your computer** in
Docker Desktop's settings. Compose's `restart: unless-stopped` policy restarts
the existing scheduler when Docker starts, unless you explicitly stopped it.
This provides startup after login; it does not run Docker before login. See
[Docker Desktop settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
and [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/).

The computer must be awake and Docker running at 17:45. Missed hourly runs are
recovered by the next run and by the report's own catch-up ingestion; a missed
17:45 report is skipped, and starting the container does not generate one. To
run manually:

```bash
docker compose exec scheduler python -m scripts.run_daily_workflow --mode ingest
docker compose exec scheduler python -m scripts.run_daily_workflow --mode report
```

`--mode report` is the default.

Every invocation computes fresh UTC timestamps ending at the actual invocation
time: the last 2 hours for ingestion, or the current Istanbul calendar day for
the report. It overrides configured `INGEST_*_TIME`, `REPORT_*_TIME`,
`DATABASE_URL`, and `REPORT_OUTPUT_PATH` values for that invocation. Events are
stored in the SQLite database `/app/output/data/activity-reporter.db` on the
output volume. There is no retention limit yet, so the file grows with each
day's events. No PostgreSQL container or migration is needed for a fresh volume;
schema changes to an existing database still require `alembic upgrade head`.

For the report, ingestion must finish before report generation, and generation
must succeed before the existing Telegram sender reads the report. If only some
sources or repositories fail during the report's own ingestion, the report is
still generated from the stored events and sent, with a plain-text `Data notice`
appended by the workflow (not the LLM) that names what could not be refreshed.
The notice also lands in the saved report file. An ingestion that cannot start at
all, a timeout, or a failed report generation still stops the run and notifies
Telegram. Reports are split into messages by the Telegram sender. Report failures and the 30-minute workflow
timeout trigger a best-effort Telegram notification naming the failed stage and
run time. A notification request can take up to 30 additional seconds.

`python -m activity_reporter ingest` exits with status 2 when it stored what it
could but some sources failed, and with 1 for fatal errors. With
`--failures-output PATH` it writes the failed sources and their failures to PATH
as JSON; the daily workflow uses this for the data notice.

Hourly ingestion failures, including partial ones, are logged and count toward
the failure streak. Telegram is notified only on the third
consecutive failure, and the streak resets after a successful run. Workflows do
not lock against each other: SQLite allows one writer at a time, so an
overlapping manual and scheduled run (or a very slow ingestion colliding with
the report) can fail with `database is locked`. Avoid starting manual runs
near the top of the hour or at 17:45.

Reports and logs persist in the `activity-reporter-output` Compose volume:

- `/app/output/data/activity-reporter.db`: stored events.
- `/app/output/state/ingest-failures`: consecutive hourly ingestion failure count.
- `/app/output/state/ingest-status.json`: failed sources from the latest ingestion.
- `/app/output/reports/activity-report.txt`: latest generated report.
- `/app/output/logs/activity-reporter.txt`: application logs, appended each run.
- `/app/output/logs/daily-workflow.log`: workflow status and date windows.

Application logs accumulate; remove or archive them periodically if needed.
Docker console logs are rotated automatically. Inspect status and copy output:

```bash
docker compose logs --tail=100 scheduler
docker compose cp scheduler:/app/output ./output
```

Configuration is injected at container creation, excluded from the image, and
preserved in a restricted runtime file so cron receives it. After changing
`.env`, recreate the scheduler with `docker compose up -d --force-recreate`.
After code or dependency changes, rebuild with `docker compose up -d --build`.
Stop scheduling with `docker compose stop`; resume with `docker compose up -d`.
The output volume remains when the container is stopped or removed.

## Adding a source

Add an adapter under `activity_reporter/adapters/` and an `EventSource` subclass under `activity_reporter/sources/`. Implement `from_environment`, `fetch`, and `adapt`, and give the source a unique name. Source modules are discovered automatically, so shared ingestion, database, query, reporting, and CLI code need no changes.
