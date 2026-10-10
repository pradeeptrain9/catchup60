#!/usr/bin/env bash
# One-time setup. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

# kokoro-onnx supports >=3.10,<3.14. The system python3 may be newer, so look
# for a compatible interpreter rather than failing on whatever `python3` is.
pick_python() {
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info < (3,14) else 1)' 2>/dev/null; then
        command -v "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

PY="$(pick_python || true)"
if [ -z "$PY" ]; then
  echo "No Python between 3.10 and 3.13 found (kokoro-onnx does not support 3.14)." >&2
  echo "Install one, e.g.  brew install python@3.12" >&2
  echo "The engine alone works on any Python 3.11+; only speech needs the ceiling." >&2
  exit 1
fi
echo "==> using $PY ($("$PY" -V 2>&1))"

if [ ! -d .venv ]; then
  echo "==> creating virtualenv"
  "$PY" -m venv .venv
fi

echo "==> installing dependencies"
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements-dev.txt

echo "==> installing speech dependencies"
if ! ./.venv/bin/python -m pip install --quiet -r requirements-tts.txt; then
  echo "    speech deps failed to install — the engine still works."
  echo "    ./run recap and ./run synthetic are unaffected; only --audio needs these."
fi

# Kokoro weights. Shared with other projects via CATCHUP60_KOKORO_DIR if set.
MODELS="${CATCHUP60_KOKORO_DIR:-cache/models}"
mkdir -p "$MODELS"
base=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
if [ ! -s "$MODELS/kokoro-v1.0.onnx" ] || [ ! -s "$MODELS/voices-v1.0.bin" ]; then
  echo "==> kokoro TTS model (~330MB, one time)"
  [ -s "$MODELS/kokoro-v1.0.onnx" ] || curl -fL --progress-bar -o "$MODELS/kokoro-v1.0.onnx" "$base/kokoro-v1.0.onnx"
  [ -s "$MODELS/voices-v1.0.bin" ]  || curl -fL --progress-bar -o "$MODELS/voices-v1.0.bin"  "$base/voices-v1.0.bin"
else
  echo "==> kokoro model already present in $MODELS"
fi

echo
echo "Done. Next:"
echo "  ./run doctor"
echo "  ./run synthetic --summary"
echo "  ./run synthetic --audio --summary     # with narration"
