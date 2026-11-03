param([switch]$SkipVision,[switch]$SkipFrontend,[string]$Python='')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
function CheckedPython([string]$Executable,[string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Python command failed. Check the error above.' }
}
New-Item -ItemType Directory -Force -Path 'work/tmp','work/bin' | Out-Null
$env:TEMP=(Resolve-Path 'work/tmp').Path
$env:TMP=$env:TEMP
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    if ($Python) {
        CheckedPython $Python @('-c','import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 is required"')
        CheckedPython $Python @('-m','venv','.venv')
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        CheckedPython 'py' @('-3.12','-m','venv','.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        CheckedPython 'python' @('-c','import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 is required"')
        CheckedPython 'python' @('-m','venv','.venv')
    } else { throw 'Install Python 3.12 or pass -Python with its absolute executable path.' }
}
$apiPython=(Resolve-Path '.venv/Scripts/python.exe').Path
CheckedPython $apiPython @('-m','pip','install','-r','requirements.txt')
if (-not $SkipFrontend) {
    $npmCommand=Get-Command npm.cmd,npm -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($npmCommand) {
        & $npmCommand.Source --prefix web ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        & $npmCommand.Source --prefix web run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } elseif (-not (Test-Path -LiteralPath 'web/dist/index.html')) {
        throw 'A source checkout requires Node.js 24 with npm. Install it, then run setup.cmd again.'
    } else { Write-Host 'Using the included frontend build; npm was not found.' }
}
if (-not $SkipVision) {
    if (-not (Test-Path -LiteralPath 'work/vision-env/Scripts/python.exe')) {
        CheckedPython $apiPython @('-m','venv','work/vision-env')
    }
    $visionPython=(Resolve-Path 'work/vision-env/Scripts/python.exe').Path
    CheckedPython $visionPython @('-m','pip','install','-r','vision/requirements-cpu.txt')
    CheckedPython $apiPython @('vision/download_model.py')
    if (-not (Test-Path -LiteralPath 'work/bin/ffmpeg.exe')) {
        $bundledFfmpeg=(& $visionPython -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())').Trim()
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $bundledFfmpeg)) { throw 'FFmpeg preparation failed.' }
        Copy-Item -LiteralPath $bundledFfmpeg -Destination 'work/bin/ffmpeg.exe'
    }
    CheckedPython $visionPython @('vision/prepare_cpu.py')
}
if (-not (Test-Path -LiteralPath '.env.local')) { Copy-Item -LiteralPath '.env.example' -Destination '.env.local' }
$requiredMode=if ($SkipVision) { 'api' } else { 'all' }
CheckedPython $apiPython @('scripts/doctor.py','--require',$requiredMode)
Write-Host 'Setup complete. Optional live Q&A uses your own key from ignored .env.local.'
Write-Host 'Start with the root launch CMD. Never include .env.local in a public repository.'
