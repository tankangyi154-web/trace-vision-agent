$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
function CheckedGpuPython([string]$Executable,[string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'GPU preparation failed. The CPU environment is retained.' }
}
if (-not (Test-Path -LiteralPath 'work/vision-gpu-env/Scripts/python.exe')) {
    if (Test-Path -LiteralPath '.venv/Scripts/python.exe') {
        CheckedGpuPython '.venv/Scripts/python.exe' @('-m','venv','work/vision-gpu-env')
    } elseif ((Test-Path -LiteralPath 'PORTABLE-MANIFEST.json') -and (Test-Path -LiteralPath 'work/vision-env/Scripts/python.exe')) {
        # Embedded Python has no venv module. Copy only its core, keeping CPU libraries separate.
        New-Item -ItemType Directory -Force -Path 'work/vision-gpu-env/Scripts/Lib/site-packages' | Out-Null
        Get-ChildItem -LiteralPath 'work/vision-env/Scripts' -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination 'work/vision-gpu-env/Scripts'
        }
    } else { throw 'Prepare the CPU runtime first with setup.cmd.' }
}
$traceGpuPython=(Resolve-Path 'work/vision-gpu-env/Scripts/python.exe').Path
if (Test-Path -LiteralPath 'work/vision-gpu-env/ready.json') { Remove-Item -LiteralPath 'work/vision-gpu-env/ready.json' }
if ((Test-Path -LiteralPath 'PORTABLE-MANIFEST.json') -and -not (Test-Path -LiteralPath 'work/vision-gpu-env/pyvenv.cfg')) {
    $traceCpuPython=(Resolve-Path 'work/vision-env/Scripts/python.exe').Path
    $traceGpuSite=(Resolve-Path 'work/vision-gpu-env/Scripts/Lib/site-packages').Path
    CheckedGpuPython $traceCpuPython @('-m','pip','install','--ignore-installed','--target',$traceGpuSite,'-r','vision/requirements-gpu.lock.txt','--extra-index-url','https://download.pytorch.org/whl/cu128')
} else {
    CheckedGpuPython $traceGpuPython @('-m','pip','install','-r','vision/requirements-gpu.lock.txt','--extra-index-url','https://download.pytorch.org/whl/cu128')
}
CheckedGpuPython $traceGpuPython @('vision/verify_gpu.py')
Write-Host 'GPU inference verified. Restart the local server to use it.'
