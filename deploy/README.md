# Deploying the recap API

```bash
./deploy/deploy.sh
```

That is the whole thing. It needs the AWS CLI and nothing else — no SAM, no
CDK. It prints the API URL at the end.

```
Lambda (python3.12) ── Polly  one call, SSML speech marks
   │                 └─ Bedrock  phrasing, under the numeric guard
   ├── HTTP API (API Gateway)   JSON
   └── S3                       narration mp3s + cached manifests
```

## Why deploy at all

The local server is two listeners on two ports because Vega's media player
refuses `http` and its `fetch` refuses the self-signed certificate the media
pipeline accepts. The TV app carries a rewrite to move audio URLs between them
(`tv/src/api.ts`, `AUDIO_ORIGIN`).

API Gateway terminates a real certificate and S3 serves Range requests
natively, which is the other thing that player insists on. Both hacks stop
being necessary on this path, so the deployed build is simpler than the local
one rather than more complicated.

## What differs from `./run serve`

| | local | deployed |
|---|---|---|
| speech | `speech/kokoro.py` (free) or `speech/polly.py` | `speech/polly_ssml.py` |
| timings | ffprobe, per segment | Polly SSML speech marks |
| audio delivery | own listener, hand-rolled 206 | presigned S3 GET |
| manifest cache | `cache/recaps/*.json` | S3 `manifests/` |

Lambda has no ffmpeg and no ffprobe, and Kokoro's 325MB of ONNX does not fit
the 250MB unzipped limit, so neither local speech path can be lifted as-is.
`speech/polly_ssml.py` exists for exactly this: one request, with a `<mark>`
before every segment, and the marks are the timings. Same accounting as
Kokoro's — each duration carries its own trailing gap and the last carries
none — so manifests from the two paths are interchangeable.

## Point the app at it

`tv/src/api.ts`: replace `HOST`/`API`/`AUDIO_ORIGIN` with the printed URL. The
two-origin split goes away; audio URLs arrive absolute and already signed, so
`audioUrl()`'s rewrite becomes a no-op.

## Access to the models

Polly works on any activated account. Bedrock needs two things that are not
IAM and cannot be done from the CLI:

1. The **Anthropic use case details** form, once per account, in the Bedrock
   console under Model access. Until it is on file every Anthropic model
   returns `AccessDeniedException: Model use case details have not been
   submitted for this account`.
2. For some models, a separate agreement — `anthropic.claude-opus-5 is not
   available for this account` even while `list-foundation-models` reports it
   `ACTIVE`.

Neither blocks a deploy. `Narrator=bedrock` is safe to leave on: a refusal
falls back to the deterministic narrator and the manifest says so in
`narrationSource` and `narrationFallback`. See `FRICTION.md` entry 12.

Note `BedrockModel` wants an **inference profile** ID (`us.anthropic.…`), not
a model ID. Bedrock reports every Anthropic model as `INFERENCE_PROFILE`-only,
so the ID printed by `list-foundation-models` is guaranteed to fail; the
callable one comes from `list-inference-profiles`.

## Verify

```bash
URL=$(aws cloudformation describe-stacks --stack-name catchup60 \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' --output text)
curl -s "$URL/playable" | python3 -m json.tool | head -20
```

```bash
curl -s "$URL/recap/synthetic" | python3 -c 'import json,sys; m=json.load(sys.stdin); print(m["totalSeconds"], m["narrationSource"], m["timingSource"]); print(m["audioUrl"][:80])'
```

Expect `totalSeconds` in 50–60, `timingSource: tts`, and an audio URL that
plays. Ask twice for the same game and at-bat: the second is a cache hit, so
it returns without paying Polly, with a freshly signed URL.

## Tear down

```bash
aws s3 rm "s3://$(aws cloudformation describe-stacks --stack-name catchup60 \
  --query 'Stacks[0].Outputs[?OutputKey==`Bucket`].OutputValue' --output text)" --recursive
aws cloudformation delete-stack --stack-name catchup60
```

The bucket must be emptied first; CloudFormation will not delete a bucket with
objects in it. Recaps expire after 7 days on their own.
