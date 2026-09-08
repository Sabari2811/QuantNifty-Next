$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Test-Path ".env.local")) {
    Write-Error "Missing .env.local. Copy .env.example to .env.local and add INDSTOCKS_API_TOKEN and DATABASE_URL. Never commit .env.local."
}

Get-Content ".env.local" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($name) { Set-Item -Path "Env:$name" -Value $value }
    }
}

if (-not $env:INDSTOCKS_API_TOKEN) { Write-Error "INDSTOCKS_API_TOKEN is not set in .env.local" }
if (-not $env:DATABASE_URL) { Write-Error "DATABASE_URL is not set in .env.local; local validation requires durable PostgreSQL evidence." }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating local Python virtual environment..."
    py -3.11 -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install -e "./apps/api"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host "Starting QuantNifty Next locally on http://127.0.0.1:8000"
Write-Host "READ-ONLY mode: no order execution is enabled."
& ".venv\Scripts\python.exe" -m uvicorn quantnifty.main:app --host 127.0.0.1 --port 8000
