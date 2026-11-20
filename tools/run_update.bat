@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set PY=python
where python >nul 2>nul || set PY=py
echo ===== %date% %time% ===== >> tools\update.log
%PY% tools\update_lawdb.py --push >> tools\update.log 2>&1
%PY% tools\snapshot_from_lawdb.py >> tools\update.log 2>&1
git add law_snapshot.json >> tools\update.log 2>&1
git commit -m "법령 스냅샷 갱신" >> tools\update.log 2>&1
git push >> tools\update.log 2>&1
