# AWS FinOps Agent

An AI FinOps agent built on the [Strands Agents SDK](https://strandsagents.com) and Amazon
Bedrock. It connects to your AWS account(s) with your **local credentials** and answers:
what's my bill, where is the money going (cost per service with double-click drill-down),
how do I spend less, and is anything anomalous.

- **Design:** see [`SPEC.md`](./SPEC.md) (read this first).
- **Working agreement:** see [`CLAUDE.md`](./CLAUDE.md) — every change is a PR; no secrets in git.

## Status
**Phase 0 — scaffold.** AWS session layer (profile / env / assume-role), model router
(Bedrock w/ fallback), and a `preflight` smoke check (STS identity + Bedrock availability).

## Quick start
```bash
cp .env.example .env          # edit; never commit .env
make install                  # installs finops_core + deps
make preflight                # verifies AWS identity + Bedrock model access
```

### Docker
```bash
make docker-build
make docker-preflight         # runs preflight in a container (mounts ~/.aws read-only)
make sandbox-preflight        # hardened: read-only FS, dropped caps, no-new-privileges
```

## Credentials (configurable)
Set `FINOPS_AWS_AUTH` to one of:
- `profile` — named profile from `~/.aws` (default; mounted read-only in Docker)
- `env` — `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`
- `assume_role` — base creds assume `FINOPS_ROLE_ARN` (best for org / multi-account)

## Modes
`FINOPS_MODE` = `advisory` (read-only, default) · `artifacts` (read-only + generated fix
scripts) · `guarded_write` (allowlisted actions with human confirmation).
