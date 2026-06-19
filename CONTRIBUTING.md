# Contributing

Thanks for contributing to the AWS FinOps Agent. Please read [`SPEC.md`](./SPEC.md) (design)
and [`CLAUDE.md`](./CLAUDE.md) (agent working agreement) before starting.

## Golden rules
- **Every change ships as a Pull Request.** Never push directly to `main`.
- **Commit & merge only after explicit reviewer/owner approval.**
- **Never commit secrets.** No AWS keys, `.env`, `~/.aws`, session tokens, real account IDs,
  or billing/customer data. Run the secret check below before every commit.
- **Read-only by default.** New AWS capabilities default to read-only. Any write action must be
  allowlisted, dry-run previewed, and human-confirmed.
- **Numbers must be exact** — never present LLM-estimated figures as billing facts.

## Workflow
1. Branch from `main`: `phase-N/<topic>` or `feat/<topic>` / `fix/<topic>`.
2. Implement with type hints; add/adjust tests under `tests/`.
3. Run locally:
   ```bash
   make fmt        # ruff
   make test       # pytest
   make preflight  # AWS identity + Bedrock check
   ```
4. Secret check before commit:
   ```bash
   git diff --cached --name-only | grep -iE '(^|/)\.env$|credential|\.aws/|\.pem$|secret|\.key$' \
     && echo "SECRET STAGED — STOP" || echo "clean"
   ```
5. Commit with a clear message; open a PR using the template; fill the checklist.
6. Address review; squash-merge after approval. Update `SPEC.md` if scope changed.

## Conventions
- Python 3.11+, `ruff` (line length 100). Dataclasses for normalized tool results.
- boto3 clients via `finops_core.aws.session.client` (adaptive retries); Cost Explorer uses `us-east-1`.
- Never hardcode Bedrock model IDs — use `config/models.yaml` / `ModelRouter`.
- Tool wrappers stay thin and typed — one AWS concern each; the same function serves UI and agent.

## Commit sign-off
Agent-authored commits include:
```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```
