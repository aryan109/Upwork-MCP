# Register Windows Scheduled Task for Aryan Upwork Resilient Local Tier
# Triggers: At logon and every 15 minutes
# Executes: python -m aryan_implementation.engine.tick --tier local
# Execution Limit: 10 minutes
# Logs: %USERPROFILE%\upwork_engine\logs\local_tick.log

$ErrorActionPreference = "Stop"
$taskName = "AryanUpworkLocalTier"
$repoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$pythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    $pythonExe = "python.exe"
}

$logDir = Join-Path $env:USERPROFILE "upwork_engine\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "local_tick.log"

Write-Host "Registering Windows Scheduled Task: $taskName" -ForegroundColor Cyan
Write-Host "Repository Root: $repoRoot" -ForegroundColor Gray
Write-Host "Python Executable: $pythonExe" -ForegroundColor Gray
Write-Host "Log file: $logFile" -ForegroundColor Gray

$actionArg = "/c cd /d `"$repoRoot`" && set ENGINE_TIER=local&& `"$pythonExe`" -m aryan_implementation.engine.tick --tier local --budget 90 >> `"$logFile`" 2>&1"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $actionArg -WorkingDirectory $repoRoot

$triggerLogon = New-ScheduledTaskTrigger -AtLogOn
$triggerInterval = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($triggerLogon, $triggerInterval) `
    -Settings $settings `
    -Principal $principal `
    -Description "Aryan Upwork Acquisition Pipeline Local Tier Watchdog & Fail-Safe Hunter" `
    -Force | Out-Null

Write-Host "Task '$taskName' registered successfully!" -ForegroundColor Green
Write-Host "Verify status: Get-ScheduledTask -TaskName '$taskName'" -ForegroundColor Yellow
Write-Host "Run on demand: Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Yellow
