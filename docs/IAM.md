# IAM setup — stop using root

The agent should run as a **dedicated least-privilege IAM principal**, not root. Preflight
warns when it detects root credentials.

## Quick start (read-only)
```bash
# Run once with credentials that can manage IAM (e.g. current root):
./scripts/setup_finops_iam.sh                 # user=finops-agent, profile=finops, us-east-1
AWS_PROFILE=finops aws sts get-caller-identity # verify
# point the agent at it:
echo "AWS_PROFILE=finops" >> .env             # or FINOPS_AWS_PROFILE=finops
make preflight
```
This creates IAM user `finops-agent`, attaches `iam/finops-readonly-policy.json` inline, mints
an access key, and writes a local `[finops]` profile (the key is never committed — `~/.aws` and
`.env` are git-ignored).

## Policies
- **`iam/finops-readonly-policy.json`** — everything the agent needs read-only: Cost Explorer,
  Budgets, Free Tier, Pricing, Compute Optimizer, Cost Optimization Hub, Trusted Advisor,
  Organizations, CUR/Athena/Glue read, S3 read, and Bedrock invoke.
  - Tighten `CurAndAthenaOutputS3Read` `Resource: "*"` to your **CUR bucket + Athena output
    bucket** ARNs in production.
- **`iam/finops-guarded-write-policy.json`** — scoped writes for `guarded_write` mode only
  (budgets, anomaly monitors, enrollment toggles, tag-scoped idle cleanup, CUR provisioning).
  **Attach only when you enable `FINOPS_MODE=guarded_write`** — not needed for advisory use.

## Multi-account / Organizations
Prefer a `FinOpsReadOnly` **role** in each linked account that trusts the runner principal, and
set `FINOPS_AWS_AUTH=assume_role` + `FINOPS_ROLE_ARN=...`. See `SPEC.md` §13.2.

## Hardening checklist
- [ ] Created `finops-agent` (or a role) with the read-only policy
- [ ] Switched the agent to the `finops` profile / assume-role
- [ ] Removed root access keys; enabled root MFA
- [ ] Scoped the S3 read statement to the CUR/Athena buckets
