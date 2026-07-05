param(
    [switch]$Send
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Cli = Join-Path $ProjectRoot "assistant_cli.py"
$LogDir = Join-Path $ProjectRoot "data\logs"
$LogFile = Join-Path $LogDir ("reminder-job-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $ProjectRoot

if ($Send) {
    & $Python $Cli reminder-job --send *>> $LogFile
} else {
    & $Python $Cli reminder-job *>> $LogFile
}
