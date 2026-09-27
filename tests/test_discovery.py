import unittest

from activity_reporter.sources.discovery import discover_sources


class DiscoveryTest(unittest.TestCase):
    def test_discovers_only_configured_sources(self) -> None:
        sources = discover_sources({"GITHUB_REPOSITORIES": "example/project"})

        self.assertEqual([source.name for source in sources], ["github"])


if __name__ == "__main__":
    unittest.main()
