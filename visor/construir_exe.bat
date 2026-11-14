@echo off
REM Builds "NBA Forecast Viewer.exe" with the project's virtual environment.
REM Just double-click it. The exe ends up in the dist\ folder of the project.
cd /d "%~dp0.."
echo Installing PyInstaller in .venv (only the first time)...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 goto error
echo Building the exe (takes about a minute)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "NBA Forecast Viewer" ^
  --icon "%cd%\visor\nba.ico" ^
  --add-data "%cd%\visor\nba.ico;." ^
  --add-data "%cd%\visor\fonts;fonts" ^
  --distpath dist --workpath build --specpath build ^
  "%cd%\visor\visor.py"
if errorlevel 1 goto error
echo.
echo Done: %cd%\dist\NBA Forecast Viewer.exe
explorer dist
pause
exit /b 0
:error
echo.
echo Something failed. Copy the text above and send it to Claude.
pause
exit /b 1
