# Register Windows Scheduled Task for Aryan Upwork Resilient Local Tier
# Triggers: At logon, on session unlock, and every 15 minutes
# Executes: python -m aryan_implementation.engine.tick --tier local
# Execution Limit: 10 minutes

$ErrorActionPreference = "Stop"
$taskName = "AryanUpworkLocalTier"
$repoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$pythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    $pythonExe = "python.exe"
}

Write-Host "Registering Windows Scheduled Task: $taskName" -ForegroundColor Cyan
Write-Host "Repository Root: $repoRoot" -ForegroundColor Gray
Write-Host "Python Executable: $pythonExe" -ForegroundColor Gray

# Action runs python -m aryan_implementation.engine.tick --tier local from repo directory
$actionArg = "/c cd /d `"$repoRoot`" && `"$pythonExe`" -m aryan_implementation.engine.tick --tier local"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $actionArg -WorkingDirectory $repoRoot

# Triggers:
# 1. At user logon
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn

# 2. Every 15 minutes indefinitely
$triggerInterval = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)

# Settings: battery allowed, 10-minute limit
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

# Register or update task
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($triggerLogon, $triggerInterval) `
    -Settings $settings `
    -Description "Aryan Upwork Acquisition Pipeline Local Tier Watchdog & Fail-Safe Hunter" `
    -Force

Write-Host "Task '$taskName' registered successfully!" -ForegroundColor Green
Write-Host "Verify status: Get-ScheduledTask -TaskName '$taskName'" -ForegroundColor Yellow
Write-Host "Run on demand: Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Yellow
