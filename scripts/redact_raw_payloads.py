"""Redact retained payloads without logging their contents."""

import json
from pathlib import Path

from sqlalchemy import text

from activity_reporter.config import DatabaseSettings, environment
from activity_reporter.database import build_repository
from activity_reporter.redaction import redact_payload


def redact_snapshot(path: Path) -> int:
    if not path.exists():
        return 0
    rewritten = []
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        event["payload"] = redact_payload(event["payload"])
        rewritten.append(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    path.write_text("\n".join(rewritten) + ("\n" if rewritten else ""), encoding="utf-8")
    path.chmod(0o600)
    return len(rewritten)


def redact_database() -> int:
    repository = build_repository(DatabaseSettings.from_environment(environment()).url)
    changed = 0
    with repository.engine.begin() as connection:
        rows = connection.execute(text("SELECT id, raw_payload FROM events")).mappings()
        for row in rows:
            redacted = redact_payload(row["raw_payload"])
            if redacted != row["raw_payload"]:
                connection.execute(
                    text("UPDATE events SET raw_payload = CAST(:raw_payload AS jsonb) WHERE id = :id"),
                    {"id": row["id"], "raw_payload": json.dumps(redacted)},
                )
                changed += 1
    return changed


if __name__ == "__main__":
    snapshot_count = redact_snapshot(Path("output/source-events-2026-10-07.jsonl"))
    database_count = redact_database()
    print(f"redacted snapshot events={snapshot_count}; database events={database_count}")
