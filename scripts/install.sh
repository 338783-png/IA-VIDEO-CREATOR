#!/usr/bin/env bash
# Installe les dépendances du projet (WSL / Linux). N'installe aucun logiciel système.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for c in node npm python3 ffmpeg ffprobe; do
  command -v "$c" >/dev/null || { echo "MANQUANT : $c"; exit 1; }
done
[ -f "$ROOT/.env" ] || cp "$ROOT/.env.example" "$ROOT/.env"
cd "$ROOT/backend"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
cd "$ROOT/frontend" && npm install --no-fund --no-audit
command -v ollama >/dev/null || echo "INFO : Ollama absent — l'app fonctionnera sans IA générative."
echo "Installation terminée."
