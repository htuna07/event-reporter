# Repository Instructions

## Secrets and sensitive configuration

- Never read `.env` unless the user explicitly authorizes reading it in the current request.
- Treat `.env` as secret-bearing even when a task involves configuration, ingestion, databases, or troubleshooting.
- Do not print, echo, `cat`, `sed`, copy, summarize, or otherwise expose any value from `.env`.
- Prefer checks that reveal only whether a required setting is present. Ask the user for explicit permission before inspecting a secret-bearing file or value.
- Apply the same caution to credential files, API keys, access tokens, private keys, and environment variables that may contain secrets.

## Git commits

- Every Git commit created in this repository must use the Conventional Commits format: `type(scope): imperative summary`.
- Use an optional scope only when it makes the affected area clearer, and use `!` before the colon for a breaking change (for example, `feat(api)!: remove legacy endpoint`).
- Valid types are `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, and `test`.
- Before committing, choose the type that describes the change and write a concise, lowercase imperative summary without a trailing period. Do not create a commit with a nonconforming message.
- For the detailed commit workflow, follow [the semantic-commits skill](.agents/skills/semantic-commits/SKILL.md).
