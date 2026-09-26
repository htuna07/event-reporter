# Activity Reporter

Fetch GitHub repository events for a chosen contributor and time range, normalize
them into a compact JSON format, then generate one activity report per repository
with Anthropic.

## Workflow

```text
GitHub Events API → output/raw/*.json → output/normalized/*.json → output/reports/*.txt
```

1. `main.py` fetches repository events page by page.
2. It retains events between `from_date` and `to_date`, then filters them by the
   configured GitHub actor.
3. Raw GitHub API responses are written to `output/raw`.
4. Each raw JSON array is normalized into a same-named JSON file in
   `output/normalized`.
5. Each normalized file is sent to Anthropic to create a text report in
   `output/reports`.

## Requirements

- Python 3.10 or later
- A GitHub personal access token for private repositories
- An Anthropic API key for report generation

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt requests
```

`requests` is used by the script and must currently be installed separately; add
it to `requirements.txt` if this project will be set up on other machines.

## Configuration

Create a `.env` file in the project root:

```dotenv
ANTHROPIC_API_KEY=your_anthropic_api_key
GITHUB_TOKEN_TEKNODEV=your_github_token
```

Only configure a GitHub token when the corresponding repository requires it.
Public repositories can use `None` as the third value in `owners_repositories`.

In `main.py`, adjust these values in `main()`:

```python
owners_repositories = [
    ("OWNER", "REPOSITORY", "GITHUB_TOKEN_ENV_VAR"),
    ("PUBLIC_OWNER", "PUBLIC_REPOSITORY", None),
]

from_date = datetime.datetime(2026, 9, 25, 0, 0, 0, tzinfo=UTC)
to_date = datetime.datetime(2026, 9, 25, 23, 59, 59, tzinfo=UTC)
```

Dates are interpreted as UTC. The selected actor is currently passed as
`"htuna07"` to `list_github_activities`; change that value to report on another
contributor.

## Run

```bash
python3 main.py
```

The script makes GitHub and Anthropic API requests and overwrites output files
with matching names. Keep API keys in `.env`; it is excluded from Git.

## Normalized event format

Each input file is an array of GitHub event objects. The normalizer safely reads
optional nested fields and writes only populated values. A normalized event can
contain:

```json
{
  "type": "PullRequestEvent",
  "actor": "octocat",
  "repo_name": "OWNER/REPOSITORY",
  "ref": "refs/heads/main",
  "action": "closed",
  "state": "approved",
  "pr_branch_from": "feature/example",
  "pr_branch_to": "main",
  "issue_title": "Example issue",
  "issue_comment": "Example comment",
  "org": "OWNER"
}
```

Depending on the event type, fields such as pull-request branches, issue data,
review state, and comments may be absent.

## Notes and limitations

- Events are fetched 100 at a time and pagination stops once the newest event on
  a page is older than `from_date`.
- The GitHub Events API has a limited recent-event history and is not intended
  for real-time reporting.
- Running report generation requires `ANTHROPIC_API_KEY` and consumes Anthropic
  API usage.
