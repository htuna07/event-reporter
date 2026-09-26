import os
from anthropic import Anthropic
from dotenv import load_dotenv
import requests
import json
import datetime
from pathlib import Path
import os


load_dotenv()


def call_github_events_api(owner, repository, token_env_var, page):
    token = os.environ.get(token_env_var) if token_env_var else None
    if token_env_var and not token:
        raise RuntimeError(
            f"{token_env_var} is not set. Add it to your .env file.")
    url = f"https://api.github.com/repos/{owner}/{repository}/events"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    response = requests.get(
        url,
        headers=headers,
        params={"page": page, "per_page": 100},
        timeout=30,
    )
    return response


def parse_github_timestamp(timestamp: str) -> datetime.datetime:
    """Parse a GitHub UTC timestamp into a timezone-aware datetime."""
    return datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def list_github_activities(owner: str,
                           repository: str,
                           token_env_var: str | None,
                           actor_login: str,
                           from_date: datetime.datetime,
                           to_date: datetime.datetime):
    # Fetch pages until the newest event on a page is older than from_date.
    page = 1
    events_in_time_range = []
    while True:
        response = call_github_events_api(
            owner, repository, token_env_var, page=page)
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch activities for the repository {owner}/{repository}: {response.status_code}")
        events = response.json()
        if not events:
            break

        # push only if it's in the time range
        for event in events:
            event_created_at = parse_github_timestamp(event["created_at"])
            if from_date <= event_created_at <= to_date:
                events_in_time_range.append(event)

        # stop fetching if the first event on this page is before the from_date
        newest_event_created_at = parse_github_timestamp(
            events[0]["created_at"])
        if newest_event_created_at < from_date:
            break

        page += 1

    # filter activities by actor login
    filtered_response = [event for event in events_in_time_range if event.get(
        "actor", {}).get("login") == actor_login]

    return filtered_response


def get_nested_value(data: dict, *keys: str):
    """Return a nested value, or None when any optional field is absent."""
    value = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def normalize_raw_activity_files(
        raw_directory: str | Path = "output/raw",
        normalized_directory: str | Path = "output/normalized") -> list[Path]:
    """Normalize every JSON event array in raw_directory into normalized_directory."""
    raw_directory = Path(raw_directory)
    normalized_directory = Path(normalized_directory)
    normalized_directory.mkdir(parents=True, exist_ok=True)
    normalized_files = []

    for raw_file in sorted(raw_directory.glob("*.json")):
        with raw_file.open(encoding="utf-8") as file:
            events = json.load(file)

        if not isinstance(events, list):
            raise ValueError(
                f"{raw_file} must contain an array of event objects.")

        normalized_events = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError(f"{raw_file} contains a non-object event.")

            body = {
                "type": event.get("type"),
                "actor": get_nested_value(event, "actor", "login"),
                "repo_name": get_nested_value(event, "repo", "name"),
                "ref": get_nested_value(event, "payload", "ref"),
                "action": get_nested_value(event, "payload", "action"),
                "state": get_nested_value(event, "payload", "review", "state"),
                "pr_branch_from": get_nested_value(
                    event, "payload", "pull_request", "head", "ref"),
                "pr_branch_to": get_nested_value(
                    event, "payload", "pull_request", "base", "ref"),
                "issue_title": get_nested_value(event, "payload", "issue", "title"),
                # overkill if it's too long
                # "issue_description": get_nested_value(event, "payload", "issue", "body"),
                "issue_comment": get_nested_value(event, "payload", "comment", "body"),
                "org": get_nested_value(event, "org", "login"),
            }

            # remove nulls from the body dictionary
            body = {k: v for k, v in body.items() if v is not None}

            normalized_events.append(body)

        normalized_file = normalized_directory / raw_file.name
        with normalized_file.open("w", encoding="utf-8") as file:
            json.dump(normalized_events, file, indent=4)
        normalized_files.append(normalized_file)

    return normalized_files


def generate_report(file: str):
    # ask llm to generate report from normalized activity files
    client = Anthropic(
        # This is the default and can be omitted
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )

    prompt = f"""
Analyze the given event activies in json object array format, 
then generate a simple report of what has been done in human-readible text format.
Report should include title, actions and summary parts.
Title should include actor and project informations.
Actions should be listed as bullet points, each one should start with category and continue with description.
Summary should provide an overall view of the activities performed.
If no events in the input, just write "Nothing has been done" under the title, no more.
Do not convert all events to individual texts one by one, 
group them by relevance, then create one sentence from each group to explain what has been done.
Here is the event activies:
{file}
"""

    message = client.messages.create(
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        model="claude-opus-5-5",
    )

    response = ""
    for block in message.content:
        if block.type == "text":
            response += block.text
    return response


def main():
    # Define owner and repositories in the <org-name>/<repo-name> format.
    owners_repositories = [
        ("Teknodev", "spica-hq-argocd", "GITHUB_TOKEN_TEKNODEV"),
        ("Teknodev", "spica-hq", "GITHUB_TOKEN_TEKNODEV"),
        ("Teknodev", "veripaygate-aws-infra", "GITHUB_TOKEN_TEKNODEV"),
        ("Teknodev", "spica-infra-tf", "GITHUB_TOKEN_TEKNODEV"),
        ("spica-engine", "spica", None),
        ("spica-engine", "spica-mcp-server", None),
        # Add more (owner, repository) tuples here if needed.
    ]

    UTC = datetime.timezone.utc
    from_date = datetime.datetime(2026, 9, 25, 0, 0, 0, tzinfo=UTC)
    to_date = datetime.datetime(2026, 9, 25, 23, 59, 59, tzinfo=UTC)

    Path("output/raw").mkdir(parents=True, exist_ok=True)
    for owner, repository, token_env_var in owners_repositories:
        response = list_github_activities(
            owner, repository, token_env_var, "htuna07", from_date, to_date)

        raw_file = Path("output/raw") / \
            f"github_activities_{owner}_{repository}.json"
        with raw_file.open("w", encoding="utf-8") as file:
            json.dump(response, file, indent=4)

    normalize_raw_activity_files()

    # read files under the outoput/normalized/
    for normalized_file in Path("output/normalized").glob("*.json"):
        # read file first, parse as json
        with normalized_file.open("r", encoding="utf-8") as file:
            data = json.load(file)
            print(f"Generating report for file: {normalized_file}")
            report = generate_report(json.dumps(data))
            # write it to reports as txt file
            report_file = Path("output/reports") / \
                f"{normalized_file.stem}.txt"
            report_file.parent.mkdir(parents=True, exist_ok=True)
            with report_file.open("w", encoding="utf-8") as file:
                file.write(report)
            print(report)


if __name__ == "__main__":
    main()
