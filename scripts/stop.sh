#!/usr/bin/env bash
# Arrête backend et frontend (tout le groupe de processus, y compris next-server).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for s in frontend backend; do
  f="$ROOT/.run/$s.pid"
  if [ -f "$f" ]; then
    pid="$(cat "$f")"
    if kill -TERM -- "-$pid" 2>/dev/null; then echo "$s arrêté."; else echo "$s n'était pas lancé."; fi
    rm -f "$f"
  fi
done
