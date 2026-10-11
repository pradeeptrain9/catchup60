#!/usr/bin/env bash
# Package and deploy the recap API. One tool you already have: the AWS CLI.
#
# No SAM, no CDK, no extra install — the friction log is long enough without
# adding a toolchain to read it. The cost is this script; the benefit is that
# `aws cloudformation deploy` is the only new thing anyone has to trust.
set -euo pipefail
cd "$(dirname "$0")/.."

STACK="${CATCHUP60_STACK:-catchup60}"
REGION="${AWS_REGION:-$(aws configure get region)}"
: "${REGION:?no region — aws configure set region us-east-1}"

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
CODE_BUCKET="catchup60-code-${ACCOUNT}-${REGION}"
CODE_KEY="catchup60/function.zip"

BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

echo "==> packaging into $BUILD"
cp deploy/handler.py "$BUILD/"
# The package, minus everything the deployed path cannot use: Kokoro needs
# 325MB of ONNX that will not fit the 250MB unzipped limit, and the CLI and
# local server have no caller here.
mkdir -p "$BUILD/src"
cp src/*.py "$BUILD/src/"
rm -f "$BUILD/src/cli.py" "$BUILD/src/server.py"
for package in engine narrate speech; do
  mkdir -p "$BUILD/src/$package"
  cp "src/$package"/*.py "$BUILD/src/$package/"
done
rm -f "$BUILD/src/speech/kokoro.py"
# fixtures.py reads the synthetic game from tests/fixtures, which is what makes
# /recap/synthetic work on a deployed endpoint with no network and no live game.
mkdir -p "$BUILD/tests/fixtures"
cp tests/fixtures/*.json "$BUILD/tests/fixtures/" 2>/dev/null || true
touch "$BUILD/tests/__init__.py"

# boto3 ships in the runtime and Bedrock is called through it, so httpx is the
# only bundled dependency. The wheels are still pinned to Linux: a Mac wheel in
# the zip fails at import with no useful message, and httpx's dependencies
# include compiled ones.
echo "==> fetching linux wheels"
.venv/bin/pip install --quiet \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 \
  --only-binary=:all: --target "$BUILD" \
  httpx==0.28.1

find "$BUILD" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD" -name '*.dist-info' -type d -prune -exec rm -rf {} + 2>/dev/null || true

ZIP="$BUILD/../function.zip"
rm -f "$ZIP"
(cd "$BUILD" && zip -qr "$ZIP" .)
echo "==> zip $(du -h "$ZIP" | cut -f1)"

echo "==> uploading to s3://$CODE_BUCKET/$CODE_KEY"
aws s3api head-bucket --bucket "$CODE_BUCKET" --region "$REGION" 2>/dev/null || \
  aws s3 mb "s3://$CODE_BUCKET" --region "$REGION" >/dev/null
aws s3 cp "$ZIP" "s3://$CODE_BUCKET/$CODE_KEY" --region "$REGION" >/dev/null
rm -f "$ZIP"

# Every parameter is passed explicitly, with its default read out of the
# template rather than repeated here.
#
# Both halves of that matter. Repeating the defaults in this script meant two
# places to change, and one of them stayed on a model the account was never
# granted. Omitting them instead does not help: `aws cloudformation deploy`
# sends UsePreviousValue for anything it is not given, so a parameter keeps
# whatever the last deploy set forever and CloudFormation truthfully reports
# "No changes to deploy" while serving the old value.
tpl_default() {
  awk -v key="  $1:" '
    $0 == key {found = 1; next}
    found && /^    Default:/ {sub(/^    Default: */, ""); gsub(/^"|"$/, ""); print; exit}
    found && /^  [A-Za-z]/ {exit}
  ' deploy/template.yaml
}

NARRATOR="${CATCHUP60_NARRATOR:-$(tpl_default Narrator)}"
MODEL="${CATCHUP60_BEDROCK_MODEL:-$(tpl_default BedrockModel)}"
VOICE="${CATCHUP60_POLLY_VOICE:-$(tpl_default PollyVoice)}"
: "${NARRATOR:?could not read Narrator default from template}"
: "${MODEL:?could not read BedrockModel default from template}"
echo "==> narrator=$NARRATOR model=$MODEL voice=$VOICE"

echo "==> deploying stack $STACK"
aws cloudformation deploy \
  --template-file deploy/template.yaml \
  --stack-name "$STACK" \
  --region "$REGION" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "CodeBucket=$CODE_BUCKET" \
    "CodeKey=$CODE_KEY" \
    "Narrator=$NARRATOR" \
    "BedrockModel=$MODEL" \
    "PollyVoice=$VOICE"

# CloudFormation updates the function's *code location*, not its code: the key
# is unchanged, so the resource has no diff and the old zip keeps serving.
# Pushing the new zip explicitly is the step whose absence looks like a deploy
# that silently did nothing.
echo "==> publishing code"
FUNCTION="$(aws cloudformation describe-stack-resource \
  --stack-name "$STACK" --logical-resource-id Function --region "$REGION" \
  --query 'StackResourceDetail.PhysicalResourceId' --output text)"
aws lambda update-function-code \
  --function-name "$FUNCTION" --region "$REGION" \
  --s3-bucket "$CODE_BUCKET" --s3-key "$CODE_KEY" \
  --query 'LastModified' --output text
aws lambda wait function-updated --function-name "$FUNCTION" --region "$REGION"

URL="$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' --output text)"
echo
echo "    $URL"
echo
echo "    curl -s $URL/playable | python3 -m json.tool | head"
echo "    tv/src/api.ts: set HOST to the host in that URL"
