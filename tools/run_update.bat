@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set PY=python
where python >nul 2>nul || set PY=py
echo ===== %date% %time% ===== >> tools\update.log
%PY% tools\update_snapshot.py --push >> tools\update.log 2>&1
