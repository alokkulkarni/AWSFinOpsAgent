#!/usr/bin/env bash
# Create a dedicated, least-privilege IAM principal for the FinOps Agent so you stop using
# root credentials. Creates an IAM user, attaches the read-only policy, mints an access key,
# and writes a local `finops` profile. Run with credentials that can manage IAM (e.g. root,
# once). REVIEW before running — this creates real IAM resources + an access key.
#
#   ./scripts/setup_finops_iam.sh [user_name] [profile_name] [region]
#
set -euo pipefail

USER_NAME="${1:-finops-agent}"
PROFILE="${2:-finops}"
REGION="${3:-us-east-1}"
POLICY_NAME="FinOpsReadOnly"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
POLICY_FILE="$HERE/iam/finops-readonly-policy.json"

command -v aws >/dev/null || { echo "aws CLI not found"; exit 1; }
[ -f "$POLICY_FILE" ] || { echo "missing $POLICY_FILE"; exit 1; }

echo "Caller (must be able to manage IAM):"
aws sts get-caller-identity --output table

if aws iam get-user --user-name "$USER_NAME" >/dev/null 2>&1; then
  echo "user $USER_NAME already exists — reusing"
else
  echo "creating IAM user $USER_NAME"
  aws iam create-user --user-name "$USER_NAME" \
    --tags Key=app,Value=aws-finops-agent Key=finops-managed,Value=true >/dev/null
fi

echo "attaching inline policy $POLICY_NAME (read-only)"
aws iam put-user-policy --user-name "$USER_NAME" \
  --policy-name "$POLICY_NAME" --policy-document "file://$POLICY_FILE"

echo "creating access key (store it safely — shown once)"
CREDS_JSON="$(aws iam create-access-key --user-name "$USER_NAME" --output json)"
AKID="$(printf '%s' "$CREDS_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin)["AccessKey"]["AccessKeyId"])')"
SECRET="$(printf '%s' "$CREDS_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin)["AccessKey"]["SecretAccessKey"])')"

echo "writing profile [$PROFILE] to ~/.aws (credentials are NOT committed to git)"
aws configure set aws_access_key_id "$AKID" --profile "$PROFILE"
aws configure set aws_secret_access_key "$SECRET" --profile "$PROFILE"
aws configure set region "$REGION" --profile "$PROFILE"

echo
echo "Done. Verify and switch the agent to the new profile:"
echo "  AWS_PROFILE=$PROFILE aws sts get-caller-identity"
echo "  export FINOPS_AWS_PROFILE=$PROFILE     # or set AWS_PROFILE=$PROFILE in .env"
echo "  make preflight"
echo
echo "Then, in the AWS console, REMOVE root access keys if any exist and enable root MFA."
