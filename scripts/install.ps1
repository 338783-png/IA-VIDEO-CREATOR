# Installation des dépendances (Windows natif, PowerShell). N'installe aucun logiciel système.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
foreach ($c in "node","npm","python","ffmpeg","ffprobe") {
  if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { Write-Error "MANQUANT : $c" }
}
if (-not (Test-Path "$Root\.env")) { Copy-Item "$Root\.env.example" "$Root\.env" }
Push-Location "$Root\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
Pop-Location
Push-Location "$Root\frontend"; npm install --no-fund --no-audit; Pop-Location
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Write-Host "INFO : Ollama absent - l'app fonctionnera sans IA generative." }
Write-Host "Installation terminee."
