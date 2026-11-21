#!/bin/bash
# Build the image and run check.py against it with the match sandbox flags (Linux / WSL).
# Fails unless check.py passes AND the C++ core actually loaded inside the container: the bot
# falls back to straight-line movement when the core is missing, which check.py alone can't see.
#
#   tools/check_docker.sh [image-name]
#   NO_BUILD=1 tools/check_docker.sh    # reuse an image built elsewhere (e.g. from Windows)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${1:-my-bot}"
cd "$ROOT" || exit 1
if [ -z "${NO_BUILD:-}" ]; then
  docker build -q -t "$IMAGE" . >/dev/null || { echo "docker build failed"; exit 1; }
fi
OUT="$(python3 check/check.py --map-dir /arena -- docker run --rm -i --network none --cpus 1 --memory 512m \
  --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$ROOT/arena:/arena:ro" "$IMAGE" 2>&1)"
STATUS=$?
echo "$OUT" | tail -8
if ! echo "$OUT" | grep -q "core ready"; then
  echo "FAIL: the C++ core did not load in the container (bot fell back to straight-line movement)"
  echo "$OUT" | grep -A8 "core unavailable" | head -20
  exit 1
fi
exit $STATUS
