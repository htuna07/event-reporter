"""Preserve runtime configuration for cron, then run the scheduler."""

import json
import os
from pathlib import Path


def main() -> None:
    runtime = Path("/run/activity-reporter")
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    runtime.chmod(0o700)
    environment_path = runtime / "environment.json"
    descriptor = os.open(
        environment_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
    )
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as environment_file:
        json.dump(dict(os.environ), environment_file)
    os.execv("/usr/sbin/cron", ["cron", "-f"])


if __name__ == "__main__":
    main()
