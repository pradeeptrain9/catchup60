#!/usr/bin/env bash
# Which gate is Bedrock behind today?
#
# Getting a first Anthropic call through a new AWS account meant passing four
# separate gates, each of which reports failure in a way that looks like one of
# the others. This prints which one you are actually on, so the answer is five
# seconds of reading rather than an afternoon of error-string archaeology.
set -uo pipefail
REGION="${1:-${AWS_REGION:-us-east-1}}"
MODEL="${CATCHUP60_BEDROCK_MODEL:-us.anthropic.claude-haiku-4-5-20251001-v1:0}"

echo "region:  $REGION"
echo "model:   $MODEL"
echo

printf 'use case form on file ... '
if aws bedrock get-use-case-for-model-access --region "$REGION" >/dev/null 2>&1; then
  echo "yes"
else
  echo "NO — Model catalog, an Anthropic model, Open in Playground, invoke"
fi

echo 'rate quotas:'
# The applied value, not the default. get-service-quota on a fresh account can
# hand back the default (5,000,000) while the applied value is zero, which is
# how an account with no headroom reads as an account with plenty.
#
# These are what the ThrottlingException is really about. Its message says
# "Too many tokens per day"; there is no per-day quota for this model, only
# these four, so the text points at a limit that does not exist and away from
# the four that do. All four are adjustable, which makes this a request you
# can file rather than a wait.
aws service-quotas list-service-quotas --service-code bedrock --region "$REGION" \
  --output json 2>/dev/null | python3 -c "
import json, sys
try:
    quotas = json.load(sys.stdin)['Quotas']
except Exception:
    print('  unknown'); raise SystemExit
want = '${CATCHUP60_QUOTA_MODEL:-Haiku 4.5}'.lower()
rows = [q for q in quotas
        if want in q['QuotaName'].lower() and 'per minute' in q['QuotaName'].lower()]
if not rows:
    print(f'  none listed for {want}')
for q in sorted(rows, key=lambda q: q['QuotaName']):
    print(f\"  {q['Value']:>10.0f}  adjustable={str(q.get('Adjustable')):5}  \"
          f\"{q['QuotaCode']}  {q['QuotaName']}\")
"
echo

printf 'live call ............... '
OUT="$(aws bedrock-runtime converse --region "$REGION" --model-id "$MODEL" \
  --messages '[{"role":"user","content":[{"text":"say ok"}]}]' \
  --inference-config '{"maxTokens":8}' 2>&1)"
case "$OUT" in
  *'"text"'*)                      echo "OK — Bedrock is usable" ;;
  *'use case details'*)            echo "blocked: use case form not submitted" ;;
  *'Too many tokens per day'*)     echo "blocked: rate quota is zero — request an increase on the codes above" ;;
  *'not available for this account'*) echo "blocked: model not granted — try another model ID" ;;
  *'inference profile'*)           echo "wrong ID: use the us./global. profile, not the model id" ;;
  *)                               echo "$(echo "$OUT" | tr -d '\n' | cut -c1-120)" ;;
esac
