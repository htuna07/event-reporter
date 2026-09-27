import unittest
from datetime import datetime, timezone

from activity_reporter.sources.cloudtrail import CloudTrailSource
from activity_reporter.sources.github import GitHubSource, Repository

START = datetime(2026, 9, 25, tzinfo=timezone.utc)
END = datetime(2026, 9, 26, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, body: list[dict]) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        pass

    def json(self) -> list[dict]:
        return self.body


class FakeRequestsSession:
    def __init__(self, pages: list[list[dict]]) -> None:
        self.headers: dict[str, str] = {}
        self.pages = iter(pages)
        self.calls = 0

    def get(self, url, params, timeout):
        self.calls += 1
        return FakeResponse(next(self.pages))


class FakePaginator:
    def __init__(self) -> None:
        self.arguments = None

    def paginate(self, **arguments):
        self.arguments = arguments
        yield {"Events": [{"EventId": "1", "EventTime": START}]}
        yield {"Events": [{"EventId": "2", "EventTime": END}]}


class FakeCloudTrailClient:
    def __init__(self, paginator: FakePaginator) -> None:
        self.paginator = paginator

    def get_paginator(self, name: str) -> FakePaginator:
        if name != "lookup_events":
            raise AssertionError(name)
        return self.paginator


class FakeBotoSession:
    def __init__(self, paginator: FakePaginator) -> None:
        self.paginator = paginator
        self.regions: list[str] = []

    def client(self, name: str, region_name: str) -> FakeCloudTrailClient:
        if name != "cloudtrail":
            raise AssertionError(name)
        self.regions.append(region_name)
        return FakeCloudTrailClient(self.paginator)


def github_event(identifier: str, timestamp: str) -> dict:
    return {"id": identifier, "created_at": timestamp}


class SourceTest(unittest.TestCase):
    def test_github_paginates_and_uses_half_open_range(self) -> None:
        session = FakeRequestsSession(
            [
                [
                    github_event("end", "2026-09-26T00:00:00Z"),
                    github_event("middle", "2026-09-25T12:00:00Z"),
                ],
                [
                    github_event("start", "2026-09-25T00:00:00Z"),
                    github_event("old", "2026-09-24T23:59:59Z"),
                ],
            ]
        )
        source = GitHubSource(
            (Repository("example", "project"),),
            session=session,
        )

        events = list(source.fetch(START, END))

        self.assertEqual([item["id"] for item in events], ["middle", "start"])
        self.assertEqual(session.calls, 2)

    def test_cloudtrail_uses_the_sdk_paginator(self) -> None:
        paginator = FakePaginator()
        session = FakeBotoSession(paginator)
        source = CloudTrailSource(
            ("eu-central-1",),
            ("Tuna",),
            session=session,
        )

        events = list(source.fetch(START, END))

        self.assertEqual([item["EventId"] for item in events], ["1"])
        self.assertEqual(session.regions, ["eu-central-1"])
        self.assertEqual(
            paginator.arguments,
            {
                "StartTime": START,
                "EndTime": END,
                "LookupAttributes": [
                    {
                        "AttributeKey": "Username",
                        "AttributeValue": "Tuna",
                    }
                ],
            },
        )

    def test_cloudtrail_accepts_legacy_actor_setting(self) -> None:
        source = CloudTrailSource.from_environment(
            {
                "AWS_REGIONS": "us-east-1",
                "AWS_ACTOR_USERNAME": "Tuna",
            }
        )

        self.assertEqual(source.actors, ("Tuna",))


if __name__ == "__main__":
    unittest.main()
