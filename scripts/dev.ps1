# Dev runner: starts the new services (NOT the legacy app/, run that manually on port 8000).
# Usage: powershell -File scripts/dev.ps1 [-Only auth]
param([string[]]$Only = @())

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Missing $python. Create the venv first (see AGENTS.md, Run and test)."
    exit 1
}

# Plans 2-4 add entries here: Name, Dir (under services/), Port, Module (uvicorn app path).
$services = @(
    @{ Name = "auth"; Dir = "auth"; Port = 8001; Module = "auth_service.main:app" }
)
if ($Only.Count -gt 0) { $services = @($services | Where-Object { $Only -contains $_.Name }) }
if ($services.Count -eq 0) { Write-Error "No matching services."; exit 1 }

foreach ($svc in $services) {
    $dir = Join-Path $root ("services\" + $svc.Dir)
    if (-not (Test-Path (Join-Path $dir ".env"))) {
        Write-Error "Missing $dir\.env. Copy .env.example to .env and set the required values."
        exit 1
    }
}

$procs = @()
try {
    foreach ($svc in $services) {
        $dir = Join-Path $root ("services\" + $svc.Dir)
        Write-Host ("Starting {0} on port {1}" -f $svc.Name, $svc.Port)
        $procs += Start-Process -FilePath $python -WorkingDirectory $dir -NoNewWindow -PassThru `
            -ArgumentList @("-m", "uvicorn", $svc.Module, "--port", "$($svc.Port)")
    }
    Write-Host "Press Ctrl+C to stop."
    Wait-Process -Id ($procs | ForEach-Object { $_.Id })
}
finally {
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
}
