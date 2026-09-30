from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

import boto3

from activity_reporter.adapters.cloudtrail import CloudTrailAdapter
from activity_reporter.config import comma_separated
from activity_reporter.logging import get_logger
from activity_reporter.sources.base import EventSource

logger = get_logger(__name__)


class CloudTrailSource(EventSource):
    name = "aws_cloudtrail"

    def __init__(
        self,
        regions: tuple[str, ...],
        actors: tuple[str, ...],
        session: Any = None,
    ) -> None:
        self.regions = regions
        self.actors = actors
        self.session = session or boto3.Session()
        self.adapter = CloudTrailAdapter()

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str]
    ) -> "CloudTrailSource | None":
        configured = environment.get("AWS_REGIONS")
        if not configured:
            return None
        regions = comma_separated(configured)
        if not regions:
            raise ValueError("AWS_REGIONS must contain at least one region.")
        configured_actors = environment.get("AWS_ACTORS") or environment.get(
            "AWS_ACTOR_USERNAME"
        )
        if not configured_actors:
            raise ValueError(
                "AWS_ACTORS must contain at least one actor when AWS_REGIONS is set."
            )
        actors = tuple(dict.fromkeys(comma_separated(configured_actors)))
        if not actors:
            raise ValueError("AWS_ACTORS must contain at least one actor.")
        return cls(regions=regions, actors=actors)

    def fetch(self, start: datetime, end: datetime) -> Iterable[dict[str, Any]]:
        for region in self.regions:
            logger.debug("cloudtrail.region_fetch_started", region=region)
            client = self.session.client("cloudtrail", region_name=region)
            paginator = client.get_paginator("lookup_events")
            for actor in self.actors:
                logger.debug("cloudtrail.actor_lookup_started", region=region)
                for page in paginator.paginate(
                    StartTime=start,
                    EndTime=end,
                    LookupAttributes=[
                        {
                            "AttributeKey": "Username",
                            "AttributeValue": actor,
                        }
                    ],
                ):
                    events = page.get("Events", [])
                    logger.debug(
                        "cloudtrail.page_fetched",
                        region=region,
                        event_count=len(events),
                    )
                    for event in events:
                        event_time = event.get("EventTime")
                        if not isinstance(event_time, datetime):
                            raise TypeError("CloudTrail event has no valid EventTime.")
                        if start <= event_time < end:
                            yield event
