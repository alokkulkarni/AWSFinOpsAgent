#!/usr/bin/env bash
# Create a DevOpsReadOnly role for org-wide estate fan-out: a read-only role in a MEMBER account
# that trusts the management (payer) account, so the DevOps agent can assume it and scan.
# Run this WITH credentials for the member account (or deploy org-wide via CloudFormation StackSets).
# REVIEW before running — it creates an IAM role.
#
#   ./scripts/setup_devops_role.sh <management-account-id> [role-name] [region]
set -euo pipefail

MGMT="${1:?usage: setup_devops_role.sh <management-account-id> [role-name] [region]}"
ROLE="${2:-DevOpsReadOnly}"
REGION="${3:-${AWS_REGION:-us-east-1}}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
POLICY_FILE="$HERE/iam/devops-readonly-policy.json"

command -v aws >/dev/null || { echo "aws CLI not found"; exit 1; }
[ -f "$POLICY_FILE" ] || { echo "missing $POLICY_FILE"; exit 1; }

TRUST="$(cat <<JSON
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
"Principal":{"AWS":"arn:aws:iam::${MGMT}:root"},"Action":"sts:AssumeRole"}]}
JSON
)"

echo "Creating role $ROLE (trusts management account $MGMT) ..."
aws iam create-role --role-name "$ROLE" --assume-role-policy-document "$TRUST" \
  --description "Read-only estate discovery for the DevOps agent" \
  --tags Key=app,Value=aws-devops-agent >/dev/null 2>&1 || echo "role may already exist — updating policy"
aws iam put-role-policy --role-name "$ROLE" --policy-name DevOpsReadOnly \
  --policy-document "file://$POLICY_FILE"

echo "Done. From the management account, scan the org with:"
echo "  devops scan --org --role-name $ROLE"
echo
echo "Org-wide: deploy this role to ALL members via a CloudFormation StackSet (service-managed,"
echo "targeting the organization) instead of running this per account."
