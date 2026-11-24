#!/usr/bin/env bash
# Démarre backend (FastAPI) et frontend (Next.js) en arrière-plan.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/.run"; mkdir -p "$RUN" "$ROOT/logs"
set -a; [ -f "$ROOT/.env" ] && . "$ROOT/.env"; set +a
BP="${BACKEND_PORT:-8000}"

if [ -f "$RUN/backend.pid" ] && kill -0 "$(cat "$RUN/backend.pid")" 2>/dev/null; then echo "Backend déjà lancé."; else
  (cd "$ROOT/backend" && setsid bash -c 'echo $$ > "$0"; exec .venv/bin/uvicorn app.main:app --host "$1" --port "$2"' \
      "$RUN/backend.pid" "${BACKEND_HOST:-127.0.0.1}" "$BP" > "$ROOT/logs/backend.out" 2>&1 < /dev/null &)
fi
if [ -f "$RUN/frontend.pid" ] && kill -0 "$(cat "$RUN/frontend.pid")" 2>/dev/null; then echo "Frontend déjà lancé."; else
  # Un cache issu de « next build » (fichier BUILD_ID) est incompatible avec le mode développement : on le régénère.
  if [ -f "$ROOT/frontend/.next/BUILD_ID" ]; then echo "Cache Next.js de production détecté : nettoyage."; rm -rf "$ROOT/frontend/.next"; fi
  (cd "$ROOT/frontend" && NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:$BP}" setsid bash -c 'echo $$ > "$0"; exec npm run dev -- -p 3000' \
      "$RUN/frontend.pid" > "$ROOT/logs/frontend.out" 2>&1 < /dev/null &)
fi
for i in $(seq 1 30); do curl -sf "http://127.0.0.1:$BP/api/health" >/dev/null && break; sleep 1; done
echo "Backend  : http://127.0.0.1:$BP/docs"
echo "Frontend : http://localhost:3000"
