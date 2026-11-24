#!/usr/bin/env bash
# Lance une instance ISOLÉE (ports 8100/3100, données temporaires), la remplit, prend des captures, puis l'arrête.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d /tmp/profia-ui-XXXX)"
OUT="${1:-$TMP/screens}"; mkdir -p "$OUT"
export STORAGE_DIR="$TMP/storage" EXPORTS_DIR="$TMP/exports" PROJECTS_DIR="$TMP/projects" LOGS_DIR="$TMP/logs" \
       DATABASE_URL="sqlite:///$TMP/app.db" FRONTEND_ORIGIN="http://localhost:3100"
(cd "$ROOT/backend" && exec .venv/bin/uvicorn app.main:app --port 8100 > "$TMP/backend.log" 2>&1) & BPID=$!
(cd "$ROOT/frontend" && NEXT_DIST_DIR=.next-test NEXT_PUBLIC_API_URL=http://127.0.0.1:8100 exec npx next dev -p 3100 > "$TMP/frontend.log" 2>&1) & FPID=$!
trap 'kill $BPID 2>/dev/null; pkill -P $FPID 2>/dev/null; kill $FPID 2>/dev/null; pkill -f "next dev -p 3100" 2>/dev/null || true' EXIT
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8100/api/health >/dev/null && break; sleep 1; done
"$ROOT/backend/.venv/bin/python" "$ROOT/tests/frontend/seed_demo.py" http://127.0.0.1:8100 "$TMP/work"
for i in $(seq 1 90); do curl -sf -o /dev/null http://localhost:3100 && break; sleep 1; done
cd "$ROOT/frontend" && UI_URL=http://localhost:3100 node "$ROOT/tests/frontend/screenshots.mjs" "$OUT" 1
echo "Captures : $OUT"
