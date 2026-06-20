#!/usr/bin/env bash
# Create a Bedrock Guardrail for the FinOps agent (PII anonymization + AWS-secret blocking +
# prompt-attack filter). Opt-in — REVIEW before running; it creates a real Bedrock resource.
# After it runs, set FINOPS_GUARDRAIL_ID / FINOPS_GUARDRAIL_VERSION (see docs/GUARDRAILS.md).
#
#   ./scripts/create_finops_guardrail.sh [name] [region]
set -euo pipefail

NAME="${1:-finops-agent-guardrail}"
REGION="${2:-${AWS_REGION:-us-east-1}}"

command -v aws >/dev/null || { echo "aws CLI not found"; exit 1; }

echo "Creating guardrail '$NAME' in $REGION ..."
OUT="$(aws bedrock create-guardrail --region "$REGION" --name "$NAME" \
  --blocked-input-messaging "This request was blocked by the FinOps agent guardrail." \
  --blocked-outputs-messaging "The response was blocked by the FinOps agent guardrail." \
  --content-policy-config '{"filtersConfig":[
      {"type":"PROMPT_ATTACK","inputStrength":"HIGH","outputStrength":"NONE"}]}' \
  --sensitive-information-policy-config '{"piiEntitiesConfig":[
      {"type":"EMAIL","action":"ANONYMIZE"},
      {"type":"AWS_ACCESS_KEY","action":"BLOCK"},
      {"type":"AWS_SECRET_KEY","action":"BLOCK"}]}' \
  --output json)"

GID="$(printf '%s' "$OUT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["guardrailId"])')"
echo "Created guardrailId=$GID (version DRAFT)"
echo
echo "Point the agent at it (no restart needed for the dashboard; services need re-up):"
echo "  export FINOPS_GUARDRAIL_ID=$GID"
echo "  export FINOPS_GUARDRAIL_VERSION=DRAFT     # or publish a version: aws bedrock create-guardrail-version"
echo
echo "NOTE (compliance): Guardrail PII masking applies to the API response only — original"
echo "content is still logged to CloudWatch. Encrypt + restrict those logs for HIPAA/GDPR."
