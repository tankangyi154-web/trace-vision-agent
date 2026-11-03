param([switch]$Force)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$traceCpuPython=(Resolve-Path 'work/vision-env/Scripts/python.exe').Path
& $traceCpuPython -m pip install -r vision/requirements-cpu.txt
if ($LASTEXITCODE -ne 0) { throw 'CPU dependency preparation failed.' }
$traceArguments=@('vision/prepare_cpu.py')
if ($Force) { $traceArguments+='--force' }
& $traceCpuPython @traceArguments
if ($LASTEXITCODE -ne 0) { throw 'CPU model verification failed; the original PyTorch path is retained.' }
Write-Host 'CPU models prepared. First use compares CPU paths on this computer.'
