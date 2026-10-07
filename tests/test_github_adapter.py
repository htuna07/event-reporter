import unittest

from activity_reporter.adapters.github import GitHubAdapter


class GitHubAdapterTest(unittest.TestCase):
    def test_maps_merged_pull_request(self) -> None:
        event = GitHubAdapter().adapt(
            {
                "id": "123",
                "type": "PullRequestEvent",
                "created_at": "2026-09-25T10:30:00Z",
                "actor": {"login": "octocat"},
                "repo": {"name": "example/project"},
                "payload": {
                    "action": "closed",
                    "pull_request": {
                        "number": 42,
                        "merged": True,
                        "html_url": "https://github.com/example/project/pull/42",
                        "title": "Improve event ingestion",
                        "body": "must-not-be-retained",
                    },
                },
            }
        )

        self.assertEqual(event.external_id, "123")
        self.assertEqual(event.source, "github")
        self.assertEqual(event.actor, "octocat")
        self.assertEqual(event.action, "pull_request.merged")
        self.assertEqual(
            event.resource,
            "https://github.com/example/project/pull/42 — Improve event ingestion",
        )
        self.assertEqual(event.event_type, "pull_request")
        self.assertEqual(event.event_action, "merged")
        self.assertEqual(event.resource_type, "pull_request")
        self.assertEqual(event.resource_id, "42")
        self.assertEqual(event.title, "Improve event ingestion")
        self.assertEqual(event.raw_payload["payload"]["pull_request"]["body"], "[OMITTED]")

    def test_uses_pull_request_review_state_as_action(self) -> None:
        event = GitHubAdapter().adapt(
            {
                "id": "124",
                "type": "PullRequestReviewEvent",
                "created_at": "2026-09-25T11:00:00Z",
                "actor": {"login": "reviewer"},
                "repo": {"name": "example/project"},
                "payload": {
                    "action": "created",
                    "review": {"state": "approved"},
                    "pull_request": {"number": 42, "title": "Improve ingestion"},
                },
            }
        )

        self.assertEqual(event.action, "pull_request_review.approved")
        self.assertEqual(
            event.resource,
            "https://github.com/example/project/pull/42 — Improve ingestion",
        )

    def test_keeps_a_bounded_safe_comment_excerpt_outside_raw_payload(self) -> None:
        event = GitHubAdapter().adapt(
            {
                "id": "125",
                "type": "IssueCommentEvent",
                "created_at": "2026-09-25T11:00:00Z",
                "actor": {"login": "reviewer"},
                "repo": {"name": "example/project"},
                "payload": {
                    "action": "created",
                    "issue": {"number": 42, "title": "Improve ingestion"},
                    "comment": {"body": "Please add the migration test."},
                },
            }
        )

        self.assertEqual(event.content_excerpt, "Please add the migration test.")
        self.assertEqual(event.raw_payload["payload"]["comment"]["body"], "[OMITTED]")


if __name__ == "__main__":
    unittest.main()
