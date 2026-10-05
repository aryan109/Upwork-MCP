@echo off
REM Aryan Upwork Acquisition Pipeline - Hourly Background Runner
cd /d "%~dp0"
echo [%date% %time%] Running Upwork Hourly Hunter and Market Intelligence pass...
python -m aryan_implementation.engine.hourly_runner --once >> "%USERPROFILE%\upwork_engine\hourly_runner.log" 2>&1
echo [%date% %time%] Hourly pass complete. Log written to %USERPROFILE%\upwork_engine\hourly_runner.log
