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

# Plan 4 adds entries here: Name, Dir (under services/), Port, Module (uvicorn app path).
$services = @(
    @{ Name = "auth"; Dir = "auth"; Port = 8001; Module = "auth_service.main:app" },
    @{ Name = "journal"; Dir = "journal"; Port = 8002; Module = "journal_service.main:app" },
    @{ Name = "analytics"; Dir = "analytics"; Port = 8003; Module = "analytics_service.main:app" },
    @{ Name = "mt5"; Dir = "mt5"; Port = 8004; Module = "mt5_service.main:app" }
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

# Services that verify each other's tokens must share one JWT_SECRET_KEY (compared, never printed).
function Get-EnvValue([string]$file, [string]$key) {
    $line = Get-Content -LiteralPath $file | Where-Object { $_ -match ("^\s*" + $key + "\s*=") } | Select-Object -Last 1
    if (-not $line) { return $null }
    return ($line -replace "^[^=]*=", "").Trim().Trim('"').Trim("'")
}
$secrets = @{}
foreach ($svc in $services) {
    $secrets[$svc.Name] = Get-EnvValue (Join-Path $root ("services\" + $svc.Dir + "\.env")) "JWT_SECRET_KEY"
}
$missing = @($services | Where-Object { [string]::IsNullOrEmpty($secrets[$_.Name]) } | ForEach-Object { $_.Name })
if ($missing.Count -gt 0) {
    Write-Error ("missing JWT_SECRET_KEY in " + ($missing -join ", "))
    exit 1
}
$reference = $services[0].Name
# -cne: secrets are case-sensitive.
$differing = @($services | Where-Object { $secrets[$_.Name] -cne $secrets[$reference] } | ForEach-Object { $_.Name })
if ($differing.Count -gt 0) {
    Write-Error ("JWT_SECRET_KEY of " + ($differing -join ", ") + " differs from " + $reference + ". All services must share the same value.")
    exit 1
}

# journal and mt5 must share INGEST_SERVICE_KEY (compared case-sensitively, never printed).
$ingest = @($services | Where-Object { @("journal", "mt5") -contains $_.Name })
if ($ingest.Count -eq 2) {
    $keys = @{}
    foreach ($svc in $ingest) {
        $keys[$svc.Name] = Get-EnvValue (Join-Path $root ("services\" + $svc.Dir + "\.env")) "INGEST_SERVICE_KEY"
    }
    $noKey = @($ingest | Where-Object { [string]::IsNullOrEmpty($keys[$_.Name]) } | ForEach-Object { $_.Name })
    if ($noKey.Count -gt 0) {
        Write-Error ("missing INGEST_SERVICE_KEY in " + ($noKey -join ", "))
        exit 1
    }
    if ($keys["mt5"] -cne $keys["journal"]) {
        Write-Error "INGEST_SERVICE_KEY of mt5 differs from journal. Both services must share the same value."
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
