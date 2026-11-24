$Root = Split-Path -Parent $PSScriptRoot
foreach ($s in "frontend","backend") {
  $f = "$Root\.run\$s.pid"
  if (Test-Path $f) {
    $procId = Get-Content $f
    taskkill /PID $procId /T /F 2>$null | Out-Null
    Remove-Item $f; Write-Host "$s arrete."
  }
}
