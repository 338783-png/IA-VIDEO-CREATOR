#!/usr/bin/env bash
# PROMPT 7 : test final complet sur une instance ISOLÉE (vos projets ne sont jamais touchés).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
TMP="$(mktemp -d /tmp/profia-final-XXXX)"; OUT="$TMP/captures"; mkdir -p "$OUT" "$TMP/work"
export STORAGE_DIR="$TMP/storage" EXPORTS_DIR="$TMP/exports" PROJECTS_DIR="$TMP/projects" LOGS_DIR="$TMP/logs" \
       DATABASE_URL="sqlite:///$TMP/app.db" FRONTEND_ORIGIN="http://localhost:3100"
(cd "$ROOT/backend" && exec .venv/bin/uvicorn app.main:app --port 8100 > "$TMP/backend.log" 2>&1) & BPID=$!
(cd "$ROOT/frontend" && NEXT_DIST_DIR=.next-test NEXT_PUBLIC_API_URL=http://127.0.0.1:8100 exec npx next dev -p 3100 > "$TMP/frontend.log" 2>&1) & FPID=$!
trap 'kill $BPID 2>/dev/null; pkill -f "next dev -p 3100" 2>/dev/null; true' EXIT
"$ROOT/backend/.venv/bin/python" - "$TMP/work" <<'PY'
import sys; from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tests" / "video"))
import make_reference, make_speech_rush
w = Path(sys.argv[1]); make_speech_rush.make(w / "rush_astuces.mp4"); make_reference.make(w / "reference_tiktok.mp4")
PY
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8100/api/health >/dev/null && break; sleep 1; done
for i in $(seq 1 120); do curl -sf -o /dev/null http://localhost:3100/new && break; sleep 1; done
(cd "$ROOT/frontend" && node "$ROOT/tests/e2e/final_test.mjs" http://localhost:3100 "$TMP/work" "$OUT")
"$ROOT/backend/.venv/bin/python" "$ROOT/tests/e2e/verify_export.py" http://127.0.0.1:8100 "$OUT" "$TMP" "$ROOT/documentation/TEST-REPORT.md"
RC=$?; echo "Captures et journaux : $TMP"; exit $RC
