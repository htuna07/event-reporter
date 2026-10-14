"""Send a plain-text report from stdin to the configured Telegram chat."""

import os
import sys

import requests


def split_report(report: str, limit: int = 3_500) -> list[str]:
    chunks = []
    while len(report) > limit:
        split_at = report.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(report[:split_at].strip())
        report = report[split_at:].strip()
    if report:
        chunks.append(report)
    return chunks


def main() -> int:
    report = sys.stdin.read().strip()
    if not report:
        raise SystemExit("Generated report is empty.")

    chunks = split_report(report)
    url = (
        "https://api.telegram.org/bot"
        f"{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    )
    try:
        for index, chunk in enumerate(chunks, start=1):
            heading = "Daily activity report"
            if len(chunks) > 1:
                heading += f" ({index}/{len(chunks)})"
            response = requests.post(
                url,
                json={
                    "chat_id": os.environ["TELEGRAM_CHAT_ID"],
                    "text": f"{heading}\n\n{chunk}",
                },
                timeout=30,
            )
            response.raise_for_status()
            if response.json().get("ok") is not True:
                raise SystemExit("Telegram rejected the report message.")
    except (requests.RequestException, ValueError):
        raise SystemExit("Telegram report delivery failed.") from None

    print(f"Report sent to Telegram in {len(chunks)} message(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
