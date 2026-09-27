from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from activity_reporter.adapters.github import GitHubAdapter
from activity_reporter.config import comma_separated, parse_datetime
from activity_reporter.sources.base import EventSource


@dataclass(frozen=True, slots=True)
class Repository:
    owner: str
    name: str


class GitHubSource(EventSource):
    name = "github"

    def __init__(
        self,
        repositories: tuple[Repository, ...],
        token: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.repositories = repositories
        self.adapter = GitHubAdapter()
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            }
        )

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "GitHubSource | None":
        configured = environment.get("GITHUB_REPOSITORIES")
        if not configured:
            return None
        repositories = tuple(
            _repository(value) for value in comma_separated(configured)
        )
        if not repositories:
            raise ValueError(
                "GITHUB_REPOSITORIES must contain at least one owner/repository."
            )
        return cls(repositories=repositories, token=environment.get("GITHUB_TOKEN"))

    def fetch(self, start: datetime, end: datetime) -> Iterable[dict[str, Any]]:
        for repository in self.repositories:
            yield from self._fetch_repository(repository, start, end)

    def _fetch_repository(
        self,
        repository: Repository,
        start: datetime,
        end: datetime,
    ) -> Iterable[dict[str, Any]]:
        page = 1
        while True:
            response = self.session.get(
                f"https://api.github.com/repos/{repository.owner}/{repository.name}/events",
                params={"page": page, "per_page": 100},
                timeout=30,
            )
            response.raise_for_status()
            events = response.json()
            if not isinstance(events, list):
                raise TypeError("GitHub returned a non-list events response.")
            if not events:
                return

            timestamps = [
                parse_datetime(str(event["created_at"]), "created_at")
                for event in events
            ]
            for event, timestamp in zip(events, timestamps):
                if start <= timestamp < end:
                    yield event
            if min(timestamps) < start:
                return
            page += 1


def _repository(value: str) -> Repository:
    owner, separator, name = value.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise ValueError(
            f"Invalid GitHub repository {value!r}; expected owner/repository."
        )
    return Repository(owner=owner, name=name)
