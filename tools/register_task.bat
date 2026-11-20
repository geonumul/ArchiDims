@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a = New-ScheduledTaskAction -Execute '%~dp0run_update.bat'; $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 10am; $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable; Register-ScheduledTask -TaskName 'ArchiDims Law Snapshot' -Action $a -Trigger $t -Settings $s -Force | Out-Null"
if %errorlevel%==0 (echo 등록 완료: 매주 월요일 10시, 꺼져 있었으면 다음에 켤 때 실행) else (echo 등록 실패)
pause
