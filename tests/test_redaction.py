import unittest

from activity_reporter.redaction import REDACTED, redact_payload


class RedactionTest(unittest.TestCase):
    def test_redacts_sensitive_keys_and_omits_free_text(self) -> None:
        value = redact_payload(
            {
                "RefreshToken": "secret",
                "nested": {"code_verifier": "secret", "body": "comment"},
                "resourceArn": "arn:aws:lambda:::function:processor",
            }
        )

        self.assertEqual(value["RefreshToken"], REDACTED)
        self.assertEqual(value["nested"]["code_verifier"], REDACTED)
        self.assertEqual(value["nested"]["body"], "[OMITTED]")
        self.assertEqual(value["resourceArn"], "arn:aws:lambda:::function:processor")


if __name__ == "__main__":
    unittest.main()
