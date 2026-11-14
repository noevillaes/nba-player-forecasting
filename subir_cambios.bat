@echo off
rem Corre una sola vez: llena lineas, horarios y lesiones de la temporada, prueba el sitio y lo sube a GitHub.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
set LOG=logs\subir_cambios.log
echo === %date% %time% === > %LOG%

echo [1/4] Lineas de DraftKings, horarios y lesiones de toda la temporada (tarda unos minutos)...
".venv\Scripts\python.exe" src\lineas.py --desde 2026-10-20 >> %LOG% 2>&1
if errorlevel 1 goto fallo

echo [2/4] Momios de varias casas (si no hay clave en .env, se salta solo)...
".venv\Scripts\python.exe" src\casas.py >> %LOG% 2>&1

echo [3/4] Probando que el sitio se construye...
".venv\Scripts\python.exe" web\build.py >> %LOG% 2>&1
if errorlevel 1 goto fallo

echo [4/4] Subiendo a GitHub...
git add src web predictions run_casas_tarde.bat >> %LOG% 2>&1
git commit -m "Momios, horarios, lesiones y mejoras del sitio" >> %LOG% 2>&1
git pull --rebase >> %LOG% 2>&1
git push >> %LOG% 2>&1
if errorlevel 1 goto fallo

echo.
echo Listo. GitHub Pages publica el sitio en unos minutos.
pause
exit /b 0

:fallo
echo.
echo Algo fallo. Los detalles quedaron en %LOG%
pause
exit /b 1
