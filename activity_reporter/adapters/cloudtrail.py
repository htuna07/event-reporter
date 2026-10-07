import json
from datetime import datetime, timezone
from typing import Any

from activity_reporter.adapters.base import EventAdapter, json_safe
from activity_reporter.config import parse_datetime
from activity_reporter.domain import NormalizedEvent
from activity_reporter.redaction import redact_payload


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

        service = _service(payload, detail)
        region = _string(detail.get("awsRegion"))
        resource = _resource_detail(payload, detail, _service_label(payload, detail), region)
        event_name = str(action)
        safe_payload = json_safe(payload)
        safe_payload["CloudTrailEvent"] = detail
        return NormalizedEvent(
            external_id=str(event_id),
            source=self.source,
            timestamp=timestamp,
            actor=str(actor),
            action=event_name,
            resource=resource["display"],
            raw_payload=redact_payload(safe_payload),
            event_type=_string(detail.get("eventType")),
            event_action=event_name,
            activity_kind=_activity_kind(event_name, detail),
            outcome="failed" if detail.get("errorCode") else "succeeded",
            service=service,
            region=region,
            resource_type=resource["type"],
            resource_id=resource["id"],
            resource_name=resource["name"],
            correlation_id=_correlation_id(detail),
            attributes=_attributes(detail),
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
    return _resource_detail(payload, detail, _service_label(payload, detail), _string(detail.get("awsRegion")))["display"]


def _resource_detail(
    payload: dict[str, Any], detail: dict[str, Any], service: str, region: str | None
) -> dict[str, str | None]:
    resources = payload.get("Resources") or detail.get("resources")
    if isinstance(resources, list):
        names = [
            str(item.get("ResourceName") or item.get("ARN"))
            for item in resources
            if isinstance(item, dict) and (item.get("ResourceName") or item.get("ARN"))
        ]
        if names:
            name = ", ".join(dict.fromkeys(names))
            return {"display": name, "type": "aws_resource", "id": name, "name": name}

    request = detail.get("requestParameters")
    if isinstance(request, dict):
        keys = _RESOURCE_PARAMETER_KEYS
        values = [str(request[key]) for key in keys if request.get(key)]
        if values:
            name = ", ".join(dict.fromkeys(values))
            key = next(key for key in keys if request.get(key))
            return {"display": name, "type": key, "id": name, "name": name}

    display = f"{service}:{region}" if region else service
    return {"display": display, "type": "aws_service", "id": service, "name": service}


_RESOURCE_PARAMETER_KEYS = (
    "resourceArn", "roleArn", "bucketName", "functionName", "tableName",
    "instanceId", "groupName", "trailName", "repositoryName", "clusterName",
    "nodegroupName", "addonName", "EnvironmentId", "name",
)


def _service(payload: dict[str, Any], detail: dict[str, Any]) -> str:
    return _service_label(payload, detail).removesuffix(".amazonaws.com")


def _service_label(payload: dict[str, Any], detail: dict[str, Any]) -> str:
    return str(_first(payload.get("EventSource"), detail.get("eventSource"), "aws"))


def _activity_kind(event_name: str, detail: dict[str, Any]) -> str:
    if detail.get("readOnly") is True:
        return "read"
    if event_name.startswith(("Delete", "Terminate", "Remove", "Detach")):
        return "delete"
    if event_name.startswith(("Assume", "GetCallerIdentity", "CreateSession", "DeleteSession", "PutCredentials", "CreateOAuth")):
        return "authentication"
    return "write"


def _correlation_id(detail: dict[str, Any]) -> str | None:
    request = detail.get("requestParameters")
    if isinstance(request, dict) and request.get("SessionId"):
        return str(request["SessionId"])
    return _string(detail.get("requestID"))


def _attributes(detail: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    request = detail.get("requestParameters")
    if isinstance(request, dict):
        for key in _RESOURCE_PARAMETER_KEYS + ("updateId",):
            if request.get(key):
                values[key] = str(request[key])
    identity = detail.get("userIdentity")
    if isinstance(identity, dict):
        if identity.get("type"):
            values["principal_type"] = str(identity["type"])
        context = identity.get("sessionContext")
        if isinstance(context, dict):
            attributes = context.get("attributes")
            if isinstance(attributes, dict) and "mfaAuthenticated" in attributes:
                values["mfa_authenticated"] = str(attributes["mfaAuthenticated"])
    if detail.get("recipientAccountId"):
        values["account_id"] = str(detail["recipientAccountId"])
    if detail.get("errorCode"):
        values["error_code"] = str(detail["errorCode"])
    return values


def _string(value: Any) -> str | None:
    return str(value) if value is not None and value != "" else None


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _first(*values: Any) -> Any:
    return next((value for value in values if value is not None and value != ""), None)
