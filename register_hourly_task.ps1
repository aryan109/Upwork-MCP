# Register Windows Scheduled Task for Aryan Upwork MCP Hourly Hunter
# Runs every 1 hour in the background to ensure fastest discovery and proposal staging

$taskName = "AryanUpworkHourlyHunter"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath = Join-Path $scriptDir "run_hourly_hunt.bat"

Write-Host "Registering Windows Scheduled Task: $taskName" -ForegroundColor Cyan
Write-Host "Target Script: $batPath" -ForegroundColor Gray

# Create action
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""

# Create trigger (repeat every 1 hour indefinitely)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)

# Settings (allow running on battery, wake if needed, stop if running > 15m)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -RestartCount 3

# Register or update
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Hourly Upwork Hunter and Market Intelligence pipeline for Aryan" -Force

Write-Host "Task '$taskName' registered successfully!" -ForegroundColor Green
Write-Host "To verify: Get-ScheduledTask -TaskName '$taskName'" -ForegroundColor Yellow
Write-Host "To run manually now: Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Yellow
