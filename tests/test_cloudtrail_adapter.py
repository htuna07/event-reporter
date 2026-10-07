import json
import unittest
from datetime import datetime, timezone

from activity_reporter.adapters.cloudtrail import CloudTrailAdapter


class CloudTrailAdapterTest(unittest.TestCase):
    def test_maps_nested_identity_and_request_resource(self) -> None:
        event = CloudTrailAdapter().adapt(
            {
                "EventId": "event-1",
                "EventName": "UpdateFunctionCode",
                "EventTime": datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
                "CloudTrailEvent": json.dumps(
                    {
                        "userIdentity": {"arn": "arn:aws:iam::123:user/Tuna"},
                        "eventSource": "lambda.amazonaws.com",
                        "awsRegion": "eu-central-1",
                        "requestParameters": {
                            "functionName": "processor",
                            "RefreshToken": "must-not-be-retained",
                        },
                    }
                ),
            }
        )

        self.assertEqual(event.external_id, "event-1")
        self.assertEqual(event.source, "aws_cloudtrail")
        self.assertEqual(event.actor, "arn:aws:iam::123:user/Tuna")
        self.assertEqual(event.action, "UpdateFunctionCode")
        self.assertEqual(event.resource, "processor")
        self.assertEqual(event.service, "lambda")
        self.assertEqual(event.region, "eu-central-1")
        self.assertEqual(event.activity_kind, "write")
        self.assertEqual(event.resource_type, "functionName")
        self.assertEqual(event.raw_payload["CloudTrailEvent"], {
            "userIdentity": {"arn": "arn:aws:iam::123:user/Tuna"},
            "eventSource": "lambda.amazonaws.com",
            "awsRegion": "eu-central-1",
            "requestParameters": {"functionName": "processor", "RefreshToken": "[REDACTED]"},
        })
        self.assertEqual(event.raw_payload["EventTime"], "2026-09-25T12:00:00+00:00")

    def test_maps_aws_service_identity(self) -> None:
        event = CloudTrailAdapter().adapt(
            {
                "EventId": "event-2",
                "EventName": "Decrypt",
                "EventTime": datetime(2026, 9, 25, 13, tzinfo=timezone.utc),
                "CloudTrailEvent": json.dumps(
                    {
                        "userIdentity": {
                            "type": "AWSService",
                            "invokedBy": "service.amazonaws.com",
                        },
                        "eventSource": "kms.amazonaws.com",
                        "awsRegion": "us-east-1",
                    }
                ),
            }
        )

        self.assertEqual(event.actor, "service.amazonaws.com")
        self.assertEqual(event.action, "Decrypt")
        self.assertEqual(event.resource, "kms.amazonaws.com:us-east-1")


if __name__ == "__main__":
    unittest.main()
