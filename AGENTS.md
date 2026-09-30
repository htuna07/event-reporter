# Repository Instructions

## Secrets and sensitive configuration

- Never read `.env` unless the user explicitly authorizes reading it in the current request.
- Treat `.env` as secret-bearing even when a task involves configuration, ingestion, databases, or troubleshooting.
- Do not print, echo, `cat`, `sed`, copy, summarize, or otherwise expose any value from `.env`.
- Prefer checks that reveal only whether a required setting is present. Ask the user for explicit permission before inspecting a secret-bearing file or value.
- Apply the same caution to credential files, API keys, access tokens, private keys, and environment variables that may contain secrets.
