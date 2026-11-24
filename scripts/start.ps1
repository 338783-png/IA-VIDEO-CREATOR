# Démarre backend et frontend (Windows natif). Si le projet est dans WSL, utilisez scripts/start.sh.
$Root = Split-Path -Parent $PSScriptRoot
$Run = "$Root\.run"; New-Item -ItemType Directory -Force $Run, "$Root\logs" | Out-Null
$b = Start-Process -FilePath "$Root\backend\.venv\Scripts\uvicorn.exe" -ArgumentList "app.main:app","--host","127.0.0.1","--port","8000" `
  -WorkingDirectory "$Root\backend" -RedirectStandardOutput "$Root\logs\backend.out" -RedirectStandardError "$Root\logs\backend.err" -WindowStyle Hidden -PassThru
$b.Id | Out-File "$Run\backend.pid"
$f = Start-Process -FilePath "npm.cmd" -ArgumentList "run","dev","--","-p","3000" -WorkingDirectory "$Root\frontend" `
  -RedirectStandardOutput "$Root\logs\frontend.out" -RedirectStandardError "$Root\logs\frontend.err" -WindowStyle Hidden -PassThru
$f.Id | Out-File "$Run\frontend.pid"
Write-Host "Backend  : http://127.0.0.1:8000/docs"
Write-Host "Frontend : http://localhost:3000"
