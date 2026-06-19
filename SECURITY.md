# Security Policy

## Reporting a vulnerability
Please report suspected vulnerabilities privately to the repository owner
(**@alokkulkarni**) — open a [private security advisory](../../security/advisories/new) or
contact the owner directly. Do **not** open a public issue for security problems.

## Handling of credentials & data
This project connects to AWS using the operator's **local credentials** and is **read-only by
default**. Security expectations:

- **No secrets in git.** AWS keys, `.env`, `~/.aws`, session tokens, real account IDs, and
  billing/customer data must never be committed. Enforced via `.gitignore` / `.dockerignore`
  and a pre-commit secret check (see `CONTRIBUTING.md`).
- **Least privilege.** Use a dedicated IAM principal with the read-only policy shipped under
  `iam/` — **not root account credentials**.
- **Credentials are mounted read-only** into containers (`~/.aws:ro`) or supplied via env /
  assume-role; they are never baked into images or written to logs.
- **Account IDs are redacted** in logs/output by default (`guardrails.redact_account_ids`).
- **Write actions are gated.** Only the `guarded_write` mode can mutate resources, limited to an
  allowlist, dry-run previewed, human-confirmed, and audit-logged. The LLM cannot self-approve.
- **Athena/Cost Explorer cost guardrails** bound query spend (scan-byte caps, SELECT-only).

## Supported versions
Pre-1.0; security fixes target the `main` branch.
