from typing import Any
import re

from activity_reporter.adapters.base import EventAdapter, json_safe
from activity_reporter.config import parse_datetime
from activity_reporter.domain import NormalizedEvent
from activity_reporter.redaction import redact_payload


class GitHubAdapter(EventAdapter):
    source = "github"

    def adapt(self, payload: dict[str, Any]) -> NormalizedEvent:
        event_id = _required_string(payload, "id")
        actor = _nested_string(payload, "actor", "login")
        repository = _nested_string(payload, "repo", "name")
        event_type = _required_string(payload, "type")
        if not actor or not repository:
            raise ValueError(f"GitHub event {event_id} has no actor or repository.")

        details = payload.get("payload", {})
        details = details if isinstance(details, dict) else {}
        event_action = _event_action(event_type, details)
        resource = _github_resource(repository, event_type, details)
        return NormalizedEvent(
            external_id=event_id,
            source=self.source,
            timestamp=parse_datetime(
                _required_string(payload, "created_at"), "created_at"
            ),
            actor=actor,
            action=_action(event_type, details),
            resource=resource["display"],
            raw_payload=redact_payload(json_safe(payload)),
            event_type=_snake_case(event_type.removesuffix("Event")),
            event_action=event_action,
            activity_kind=_activity_kind(event_type, event_action),
            outcome=_outcome(event_type, event_action),
            service="github",
            resource_type=resource["type"],
            resource_id=resource["id"],
            resource_name=resource["name"],
            resource_url=resource["url"],
            title=resource["title"],
            content_excerpt=_content_excerpt(details),
            attributes=_attributes(repository, details),
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


def _event_action(event_type: str, details: dict[str, Any]) -> str | None:
    action = details.get("action")
    if event_type == "PullRequestEvent" and action == "closed":
        pull_request = details.get("pull_request")
        if isinstance(pull_request, dict) and pull_request.get("merged") is True:
            return "merged"
    if event_type == "PullRequestReviewEvent":
        review = details.get("review")
        if isinstance(review, dict) and review.get("state"):
            return str(review["state"]).lower()
    if event_type in {"CreateEvent", "DeleteEvent"}:
        return str(details["ref_type"]) if details.get("ref_type") else None
    return str(action) if action else None


def _activity_kind(event_type: str, action: str | None) -> str:
    if event_type == "PushEvent":
        return "write"
    if event_type == "DeleteEvent":
        return "delete"
    if event_type in {"PullRequestReviewEvent", "IssueCommentEvent"}:
        return "collaboration"
    if action in {"opened", "created", "published", "reopened", "closed", "merged"}:
        return "write"
    return "activity"


def _outcome(event_type: str, action: str | None) -> str | None:
    if event_type == "PullRequestEvent" and action == "merged":
        return "succeeded"
    return None


def _github_resource(repository: str, event_type: str, details: dict[str, Any]) -> dict[str, str | None]:
    category = "pull" if event_type in {"PullRequestEvent", "PullRequestReviewEvent"} else "issues"
    entity = details.get("pull_request") if category == "pull" else details.get("issue")
    if isinstance(entity, dict):
        number = entity.get("number") or details.get("number")
        url = entity.get("html_url") or (f"https://github.com/{repository}/{category}/{number}" if number is not None else None)
        title = str(entity["title"]) if entity.get("title") else None
        return {"display": f"{url} — {title}" if url and title else str(url or repository), "type": "pull_request" if category == "pull" else "issue", "id": str(number) if number is not None else None, "name": repository, "url": str(url) if url else None, "title": title}
    ref = details.get("ref")
    if ref:
        return {"display": f"{repository}@{ref}", "type": str(details.get("ref_type") or "ref"), "id": str(ref), "name": repository, "url": None, "title": None}
    return {"display": repository, "type": "repository", "id": repository, "name": repository, "url": None, "title": None}


def _attributes(repository: str, details: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {"repository": repository}
    for key in ("ref", "before", "head", "full_ref"):
        if details.get(key):
            values[key] = str(details[key])
    for entity_key in ("pull_request", "issue"):
        entity = details.get(entity_key)
        if isinstance(entity, dict):
            if entity.get("state"):
                values["state"] = str(entity["state"])
            if entity_key == "pull_request":
                values["merged"] = bool(entity.get("merged"))
                for ref_key in ("base", "head"):
                    ref = entity.get(ref_key)
                    if isinstance(ref, dict) and ref.get("ref"):
                        values[f"{ref_key}_ref"] = str(ref["ref"])
            break
    release = details.get("release")
    if isinstance(release, dict):
        for key in ("tag_name", "name"):
            if release.get(key):
                values[key] = str(release[key])
    return values


_UNSAFE_CONTENT = re.compile(
    r"(?:authorization|bearer\s+|password|secret|token|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)


def _content_excerpt(details: dict[str, Any]) -> str | None:
    for key in ("comment", "review"):
        item = details.get(key)
        if isinstance(item, dict) and isinstance(item.get("body"), str):
            body = " ".join(item["body"].split())
            if body and not _UNSAFE_CONTENT.search(body):
                return body[:280]
    return None


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
