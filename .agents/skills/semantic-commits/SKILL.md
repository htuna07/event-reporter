---
name: semantic-commits
description: Prepare and create Git commits in this repository using the required Conventional Commits message format. Use whenever a commit is requested or about to be created.
---

# Semantic Commits

All commits in this repository must conform to Conventional Commits:

```text
type(scope): imperative summary
```

`scope` is optional. Put `!` before the colon for breaking changes:

```text
feat(api)!: remove legacy endpoint
```

## Choose the message

Use exactly one of these types:

- `build`: build system or external dependencies
- `chore`: maintenance that does not fit another type
- `ci`: continuous-integration configuration
- `docs`: documentation only
- `feat`: new user-facing capability
- `fix`: bug correction
- `perf`: measurable performance improvement
- `refactor`: code restructuring with unchanged behavior
- `revert`: reverses an earlier commit
- `style`: formatting-only change with no behavior change
- `test`: test-only change

Write the summary in lowercase imperative mood, keep it concise, and omit a final period. Use a scope only when it clarifies the affected component.

Examples:

```text
feat(reports): add weekly activity summary
fix(parser): handle empty event payloads
docs: clarify local setup
test(auth): cover expired session handling
```

## Commit workflow

1. Inspect the staged changes and confirm they belong in one coherent commit.
2. Select the type, optional scope, and summary from the actual change.
3. Validate the proposed message against the required format before running `git commit`.
4. If the message cannot conform, revise it; never create a nonconforming commit.

This skill supplements the repository rule in `AGENTS.md`; the repository rule remains mandatory even when this skill is not explicitly invoked.
