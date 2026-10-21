# Football Intelligence OS — local dev stack launcher
# Starts: Postgres, MongoDB (Docker) + analytics API + identity service + dev gateway + React UI.
#   UI:        http://localhost:3005
#   Sign in:   http://localhost:8004/dev/sign-in   (drops the seeded local session cookie)
#   API:       http://localhost:8004/api/status
#   API docs:  http://127.0.0.1:8002/docs
$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot
$Logs = Join-Path $env:TEMP "opencode\fios_logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

function Test-Port($p) { [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) }

# 1. Datastores -------------------------------------------------------------
if (-not (docker ps --filter "name=fios_pg" --format "{{.Names}}" | Select-String fios_pg)) {
    docker start fios_pg 2>$null
    if ($LASTEXITCODE -ne 0) { docker run -d --name fios_pg -e POSTGRES_USER=fios -e POSTGRES_PASSWORD=fios -e POSTGRES_DB=fios -p 55432:5432 postgres:16 | Out-Null }
}
if (-not (docker ps --filter "name=fios_mongo" --format "{{.Names}}" | Select-String fios_mongo)) {
    docker start fios_mongo 2>$null
    if ($LASTEXITCODE -ne 0) { docker run -d --name fios_mongo -p 28017:27017 mongo:7 | Out-Null }
}
Write-Host "Waiting for Postgres + Mongo..." -ForegroundColor Cyan
Start-Sleep -Seconds 6

# 2. Migrations (idempotent) ------------------------------------------------
$env:DATABASE_URL = "postgresql+asyncpg://fios:fios@localhost:55432/fios"
Push-Location $Repo
alembic upgrade head *> (Join-Path $Logs "migrate.log")
Pop-Location

# 3. Backend processes ------------------------------------------------------
Start-Process python -ArgumentList "-m","uvicorn","app.main:app","--app-dir","apps/api","--host","127.0.0.1","--port","8002" -WorkingDirectory $Repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Logs "api.out.log") -RedirectStandardError (Join-Path $Logs "api.err.log")
Start-Process python -ArgumentList "-m","uvicorn","server:app","--app-dir","Football_OS-frontend/backend","--host","127.0.0.1","--port","8003" -WorkingDirectory $Repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Logs "identity.out.log") -RedirectStandardError (Join-Path $Logs "identity.err.log")
Start-Process python -ArgumentList "-m","uvicorn","dev_gateway:app","--app-dir","scratch","--host","127.0.0.1","--port","8004" -WorkingDirectory $Repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Logs "gateway.out.log") -RedirectStandardError (Join-Path $Logs "gateway.err.log")

Write-Host "Waiting for backends..." -ForegroundColor Cyan
Start-Sleep -Seconds 12

# 4. Frontend ---------------------------------------------------------------
$fe = Join-Path $Repo "Football_OS-frontend\frontend"
if (-not (Test-Path (Join-Path $fe "node_modules"))) {
    Write-Host "Installing frontend dependencies (first run, can take a few minutes)..." -ForegroundColor Cyan
    Push-Location $fe; yarn install --network-timeout 600000 *> (Join-Path $Logs "yarn_install.log"); Pop-Location
}
Start-Process cmd -ArgumentList "/c","yarn start > `"$Logs\frontend.log`" 2>&1" -WorkingDirectory $fe -WindowStyle Hidden

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " Football Intelligence OS is starting..." -ForegroundColor Green
Write-Host "   App:      http://localhost:3005" -ForegroundColor Green
Write-Host "   Sign in:  http://localhost:8004/dev/sign-in" -ForegroundColor Green
Write-Host "   API:      http://localhost:8004/api/status" -ForegroundColor Green
Write-Host "   API docs: http://127.0.0.1:8002/docs" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
