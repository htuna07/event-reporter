from typing import Any

from activity_reporter.adapters.base import EventAdapter, json_safe
from activity_reporter.config import parse_datetime
from activity_reporter.domain import NormalizedEvent


class GitHubAdapter(EventAdapter):
    source = "github"

    def adapt(self, payload: dict[str, Any]) -> NormalizedEvent:
        event_id = _required_string(payload, "id")
        actor = _nested_string(payload, "actor", "login")
        repository = _nested_string(payload, "repo", "name")
        event_type = _required_string(payload, "type")
        if not actor or not repository:
            raise ValueError(f"GitHub event {event_id} has no actor or repository.")

        return NormalizedEvent(
            external_id=event_id,
            source=self.source,
            timestamp=parse_datetime(
                _required_string(payload, "created_at"), "created_at"
            ),
            actor=actor,
            action=_action(event_type, payload.get("payload", {})),
            resource=_resource(repository, event_type, payload.get("payload", {})),
            raw_payload=json_safe(payload),
        )


def _action(event_type: str, payload: Any) -> str:
    details = payload if isinstance(payload, dict) else {}
    kind = _snake_case(event_type.removesuffix("Event"))
    action = details.get("action")
    if event_type == "PullRequestEvent" and action == "closed":
        pull_request = details.get("pull_request")
        if isinstance(pull_request, dict) and pull_request.get("merged") is True:
            action = "merged"
    if event_type == "PullRequestReviewEvent":
        review = details.get("review")
        if isinstance(review, dict) and review.get("state"):
            action = review["state"]
    if event_type in {"CreateEvent", "DeleteEvent"}:
        action = details.get("ref_type")
    return ".".join(str(part) for part in (kind, action) if part)


def _resource(repository: str, event_type: str, payload: Any) -> str:
    details = payload if isinstance(payload, dict) else {}
    if event_type in {"PullRequestEvent", "PullRequestReviewEvent"}:
        return _numbered_resource(
            repository, "pull", details.get("pull_request"), details
        )
    if event_type in {"IssuesEvent", "IssueCommentEvent"}:
        return _numbered_resource(repository, "issues", details.get("issue"), details)
    ref = details.get("ref")
    if ref:
        return f"{repository}@{ref}"
    return repository


def _numbered_resource(
    repository: str,
    category: str,
    entity: Any,
    payload: dict[str, Any],
) -> str:
    if isinstance(entity, dict):
        html_url = entity.get("html_url")
        number = entity.get("number")
        identifier = str(html_url) if html_url else None
        if not identifier and number is not None:
            identifier = f"https://github.com/{repository}/{category}/{number}"
        if identifier:
            title = entity.get("title")
            return f"{identifier} — {title}" if title else identifier
    number = payload.get("number")
    if number is not None:
        return f"https://github.com/{repository}/{category}/{number}"
    return repository


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None or value == "":
        raise ValueError(f"GitHub event is missing {key}.")
    return str(value)


def _nested_string(payload: dict[str, Any], *keys: str) -> str | None:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return str(value) if value is not None else None


def _snake_case(value: str) -> str:
    result: list[str] = []
    for index, character in enumerate(value):
        if character.isupper() and index:
            result.append("_")
        result.append(character.lower())
    return "".join(result)
