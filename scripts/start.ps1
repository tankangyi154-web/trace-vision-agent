param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Install local Python dependencies first; see README.' }
if (-not (Test-Path -LiteralPath 'web/dist/index.html')) { throw 'Build the frontend first: npm --prefix web run build' }
$url='http://127.0.0.1:8000'
try {
    $health=Invoke-RestMethod "$url/api/health" -TimeoutSec 2
    if ($health.project -eq 'video-event-agent') {
        if (-not $NoBrowser) { Start-Process $url }
        Write-Host "Local workbench is already running: $url"
        exit 0
    }
} catch { }
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'work') | Out-Null
$pythonPath=Join-Path $projectRoot '.venv/Scripts/python.exe'
& $pythonPath (Join-Path $projectRoot 'scripts/doctor.py') --require api
if ($LASTEXITCODE -ne 0) { throw 'Startup checks failed. Run setup.cmd or see README.' }
$server=Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','app:app','--host','127.0.0.1','--port','8000','--no-access-log') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'work/local-api.log') -RedirectStandardError (Join-Path $projectRoot 'work/local-api-error.log')
try {
    $ready=$false
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        if ($server.HasExited) { throw 'API startup failed; see work/local-api-error.log' }
        try {
            $health=Invoke-RestMethod "$url/api/health" -TimeoutSec 1
            if ($health.project -eq 'video-event-agent') { $ready=$true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'API did not become ready; see work/local-api-error.log' }
    if (-not $NoBrowser) { Start-Process $url }
    Write-Host "Local workbench: $url"
    Write-Host 'Keep this window open. Press Ctrl+C to stop this server.'
    Wait-Process -Id $server.Id
} finally {
    if (-not $server.HasExited) { Stop-Process -Id $server.Id }
}
