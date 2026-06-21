# DevOps / estate agent — IAM (read-only)

Estate discovery is **read-only**. Two principals are involved:

## 1) The runner (where the agent runs)
Needs read access to the discovery sources in the account it scans, plus the ability to assume
member roles for org fan-out. Use the AWS managed **`ReadOnlyAccess`** policy, or the focused
**`iam/devops-readonly-policy.json`** (Resource Explorer, Tagging API, Config aggregate, EC2/
RDS/ELB/Lambda/ECS/EKS/S3/CloudFront/Route53/API GW/DynamoDB/IAM describe+list, Organizations,
STS). For fan-out also allow `sts:AssumeRole` on the member role ARNs.

## 2) The member-account role (for `--org` fan-out)
A read-only role in each Organization member account that **trusts the management account**, so
the agent can assume it and scan. Create it with:
```bash
# run with member-account credentials (or deploy org-wide via a CloudFormation StackSet):
./scripts/setup_devops_role.sh <management-account-id> DevOpsReadOnly
# then, from the management account:
devops scan --org --role-name DevOpsReadOnly
```
`scripts/setup_devops_role.sh` creates `DevOpsReadOnly` trusting `arn:aws:iam::<mgmt>:root` and
attaches `iam/devops-readonly-policy.json`.

### Notes
- **Org-wide rollout**: deploy the role to all members via a **service-managed CloudFormation
  StackSet** targeting the organization, not per-account.
- **Control Tower** core accounts (Audit, Log Archive) often block cross-account assume via SCPs —
  the scanner notes these and continues (verified live).
- Prefer a dedicated `finops`/`devops` profile over **root** (preflight warns on root).
- Resource Explorer needs an **index** per region (and an aggregator index for cross-region
  search); Config-based discovery needs **Config recording** enabled.
