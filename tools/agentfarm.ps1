# AgentFarm brain launcher.
#
# ASCII-ONLY ON PURPOSE. Two environment facts drive this:
#   1) Windows PowerShell 5.1 decodes a BOM-less .ps1 as ANSI, which mangles any
#      non-ASCII text and turns the file into a parse error. Keeping this file
#      ASCII sidesteps the problem in both powershell.exe and pwsh.
#   2) The bare `python` on PATH is a Microsoft Store placeholder, so we resolve
#      a real interpreter explicitly (see docs/02-environment.md).
# All Chinese user-facing output comes from the Python side.
#
# Usage:
#   .\tools\agentfarm.cmd doctor
#   .\tools\agentfarm.cmd observe
#   .\tools\agentfarm.cmd move 64 15

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$brain = Join-Path $repo 'brain'

function Resolve-Python {
    if ($env:AGENTFARM_PYTHON -and (Test-Path $env:AGENTFARM_PYTHON)) { return $env:AGENTFARM_PYTHON }

    $venv = Join-Path $brain '.venv\Scripts\python.exe'
    if (Test-Path $venv) { return $venv }

    $dsh = 'C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
    if (Test-Path $dsh) { return $dsh }

    $wb = 'C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe'
    if (Test-Path $wb) { return $wb }

    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch 'WindowsApps') { return $cmd.Source }

    throw "No usable Python found. Set AGENTFARM_PYTHON to a python.exe path."
}

$python = Resolve-Python

# Force UTF-8 so Chinese output survives pipes and redirection.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Push-Location $brain
try {
    & $python -m agentfarm @Rest
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
