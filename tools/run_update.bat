@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set PY=
python -c "import sys" >nul 2>nul && set PY=python
if not defined PY ( py -3 -c "import sys" >nul 2>nul && set PY=py -3 )
if not defined PY ( echo Python 없음 >> tools\update.log & exit /b 1 )
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% ===== >> tools\update.log
git pull --rebase --autostash >> tools\update.log 2>&1
%PY% tools\update_lawdb.py --push >> tools\update.log 2>&1
%PY% tools\snapshot_from_lawdb.py >> tools\update.log 2>&1
git add law_snapshot.json >> tools\update.log 2>&1
git commit -m "법령 스냅샷 갱신" >> tools\update.log 2>&1
git push >> tools\update.log 2>&1
