@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title ArchiDims 자동 갱신 설치
echo.
echo  ArchiDims 법령 자동 갱신 설치
echo  ------------------------------
echo.

set NEED_RESTART=0

where git >nul 2>nul
if errorlevel 1 (
  echo [1/5] Git 설치 중...
  winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
  set NEED_RESTART=1
) else (
  echo [1/5] Git 확인됨
)

set PY=
python -c "import sys" >nul 2>nul && set PY=python
if not defined PY ( py -3 -c "import sys" >nul 2>nul && set PY=py -3 )
if not defined PY (
  echo [2/5] Python 설치 중...
  winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
  set NEED_RESTART=1
) else (
  echo [2/5] Python 확인됨
)

if "!NEED_RESTART!"=="1" (
  echo.
  echo  프로그램을 새로 설치했습니다. 이 창을 닫고 이 파일을 한 번 더 실행해 주세요.
  echo.
  pause
  exit /b
)

set DIR=%USERPROFILE%\ArchiDims
if exist "%DIR%\.git" (
  echo [3/5] 저장소 최신으로 받는 중...
  git -C "%DIR%" pull --rebase --autostash
) else (
  echo [3/5] 저장소 내려받는 중...
  git clone https://github.com/geonumul/ArchiDims.git "%DIR%"
)
if not exist "%DIR%\tools\update_lawdb.py" (
  echo  저장소를 받지 못했습니다. 인터넷 연결을 확인하세요.
  pause
  exit /b
)
cd /d "%DIR%"
git config user.name >nul 2>nul || git config user.name "geonumul"
git config user.email >nul 2>nul || git config user.email "geonumul@users.noreply.github.com"

if not exist tools\config.local.json (
  echo.
  set /p OC= 법제처 OPEN API 인증키^(OC^)를 입력하고 Enter: 
  echo {"oc": "!OC!"}> tools\config.local.json
)

echo.
echo [4/5] 법령과 조례를 받는 중입니다. 10분쯤 걸립니다...
echo  ^(GitHub 로그인 창이 뜨면 로그인해 주세요^)
call tools\run_update.bat
echo.
echo  --- 실행 기록 ^(마지막 12줄^) ---
powershell -NoProfile -Command "Get-Content -Tail 12 -Encoding UTF8 tools\update.log"
echo.

echo [5/5] 매주 월요일 10시 자동 실행 등록 중...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a = New-ScheduledTaskAction -Execute '%DIR%\tools\run_update.bat'; $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 10am; $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable; Register-ScheduledTask -TaskName 'ArchiDims Law Snapshot' -Action $a -Trigger $t -Settings $s -Force | Out-Null"
if errorlevel 1 ( echo  등록 실패 ) else ( echo  등록 완료 )
echo.
echo  끝났습니다. 위 실행 기록에 오류가 보이면 이 화면을 캡처해 주세요.
echo.
pause
