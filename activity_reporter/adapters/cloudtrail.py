import json
from datetime import datetime, timezone
from typing import Any

from activity_reporter.adapters.base import EventAdapter, json_safe
from activity_reporter.config import parse_datetime
from activity_reporter.domain import NormalizedEvent


class CloudTrailAdapter(EventAdapter):
    source = "aws_cloudtrail"

    def adapt(self, payload: dict[str, Any]) -> NormalizedEvent:
        detail = _detail(payload)
        event_id = _first(payload.get("EventId"), detail.get("eventID"))
        actor = _first(
            payload.get("Username"),
            _nested(detail, "userIdentity", "userName"),
            _nested(detail, "userIdentity", "arn"),
            _nested(detail, "userIdentity", "principalId"),
            _nested(detail, "userIdentity", "invokedBy"),
        )
        action = _first(payload.get("EventName"), detail.get("eventName"))
        timestamp = _timestamp(payload.get("EventTime") or detail.get("eventTime"))
        if not event_id or not actor or not action:
            raise ValueError("CloudTrail event has no id, actor, or action.")

        return NormalizedEvent(
            external_id=str(event_id),
            source=self.source,
            timestamp=timestamp,
            actor=str(actor),
            action=str(action),
            resource=_resource(payload, detail),
            raw_payload=json_safe(payload),
        )


def _detail(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("CloudTrailEvent")
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("CloudTrailEvent must be valid JSON.") from error
    return parsed if isinstance(parsed, dict) else {}


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        return parse_datetime(value, "EventTime")
    raise ValueError("CloudTrail event has no timestamp.")


def _resource(payload: dict[str, Any], detail: dict[str, Any]) -> str:
    resources = payload.get("Resources") or detail.get("resources")
    if isinstance(resources, list):
        names = [
            str(item.get("ResourceName") or item.get("ARN"))
            for item in resources
            if isinstance(item, dict) and (item.get("ResourceName") or item.get("ARN"))
        ]
        if names:
            return ", ".join(dict.fromkeys(names))

    request = detail.get("requestParameters")
    if isinstance(request, dict):
        keys = (
            "resourceArn",
            "roleArn",
            "bucketName",
            "functionName",
            "tableName",
            "instanceId",
            "groupName",
            "trailName",
            "repositoryName",
            "clusterName",
            "secretId",
            "keyId",
        )
        values = [str(request[key]) for key in keys if request.get(key)]
        if values:
            return ", ".join(dict.fromkeys(values))

    service = _first(payload.get("EventSource"), detail.get("eventSource"), "aws")
    region = detail.get("awsRegion")
    return f"{service}:{region}" if region else str(service)


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _first(*values: Any) -> Any:
    return next((value for value in values if value is not None and value != ""), None)
