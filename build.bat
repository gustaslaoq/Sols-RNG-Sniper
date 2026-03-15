@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  Slaoq's Sniper — Build & Deploy Script
::  
::  Modes:
::    build.bat              → fresh build into current folder
::    build.bat --update "C:\path\to\SlaoqSniper.exe"
::                           → rebuild + replace running .exe + restart
::
::  Flow:
::    1. Check prerequisites (Python, pip, git)
::    2. Clone repo into a temp folder
::    3. Stamp the commit SHA into main.py (for the auto-updater)
::    4. pip install dependencies
::    5. PyInstaller --onefile build
::    6. Copy .exe to destination
::    7. Create plugins/ and assets/ folders
::    8. Download assets (logo, icon)
::    9. Clean up temp folder
::   10. If --update mode: wait for old process to exit, then restart
:: ============================================================

:: ── CONFIGURE THESE ──────────────────────────────────────────────────────────
set REPO_URL=https://github.com/YOUR_USERNAME/YOUR_REPO.git
set EXE_NAME=SlaoqSniper
set PYTHON_MIN=3.10
:: ─────────────────────────────────────────────────────────────────────────────

set UPDATE_MODE=0
set TARGET_EXE=
set SCRIPT_DIR=%~dp0

if "%~1"=="--update" (
    set UPDATE_MODE=1
    set TARGET_EXE=%~2
)

:: If no target exe was given in update mode, default to script dir
if "%TARGET_EXE%"=="" (
    set TARGET_EXE=%SCRIPT_DIR%%EXE_NAME%.exe
)

echo.
echo  ==========================================
echo   Slaoq's Sniper ^| Build Pipeline
echo  ==========================================
echo.

:: ── 1. Check Python ──────────────────────────────────────────────────────────
echo [1/9] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found in PATH.
    echo  Please install Python %PYTHON_MIN%+ from https://python.org
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Python %PY_VER% found.

:: ── 2. Check Git ─────────────────────────────────────────────────────────────
echo [2/9] Checking Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Git not found in PATH.
    echo  Please install Git from https://git-scm.com
    pause
    exit /b 1
)
echo  Git found.

:: ── 3. Create temp build directory ───────────────────────────────────────────
echo [3/9] Cloning repository...
set BUILD_DIR=%TEMP%\SnipeBuild_%RANDOM%%RANDOM%
git clone --depth=1 "%REPO_URL%" "%BUILD_DIR%" 2>nul
if errorlevel 1 (
    echo  [ERROR] Failed to clone repository.
    echo  Check your internet connection and that REPO_URL is correct:
    echo  %REPO_URL%
    pause
    exit /b 1
)
echo  Cloned into %BUILD_DIR%

:: ── 4. Get current commit SHA (7 chars) ──────────────────────────────────────
cd /d "%BUILD_DIR%"
for /f %%h in ('git rev-parse --short HEAD 2^>nul') do set COMMIT_SHA=%%h
echo  Commit: %COMMIT_SHA%

:: Stamp the commit SHA into main.py so the auto-updater knows what was built
echo  Stamping commit SHA into main.py...
powershell -NoProfile -Command ^
    "(Get-Content main.py -Raw) -replace 'class AutoUpdater\(QObject\):', ^
    'class AutoUpdater(QObject):\n    _BUILT_SHA = \"%COMMIT_SHA%\"' ^
    | Set-Content main.py -NoNewline" >nul 2>&1

:: ── 5. Install dependencies ───────────────────────────────────────────────────
echo [4/9] Installing dependencies...
python -m pip install --upgrade pip --quiet
python -m pip install pyinstaller PySide6 psutil keyboard aiohttp --quiet
if errorlevel 1 (
    echo  [ERROR] pip install failed.
    pause
    exit /b 1
)
echo  Dependencies installed.

:: ── 6. Run PyInstaller ────────────────────────────────────────────────────────
echo [5/9] Building executable...

:: Determine icon path
set ICON_OPT=
if exist "assets\app.ico" set ICON_OPT=--icon=assets\app.ico

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "%EXE_NAME%" ^
    --add-data "sniper_engine.py;." ^
    %ICON_OPT% ^
    main.py

if errorlevel 1 (
    echo  [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

if not exist "dist\%EXE_NAME%.exe" (
    echo  [ERROR] Build succeeded but .exe not found in dist\.
    pause
    exit /b 1
)
echo  Build complete: dist\%EXE_NAME%.exe

:: ── 7. Copy .exe to destination ───────────────────────────────────────────────
echo [6/9] Deploying executable...

if "%UPDATE_MODE%"=="1" (
    :: In update mode: wait a moment for the old process to fully exit,
    :: then replace it in-place.
    echo  [UPDATE] Waiting for old process to exit...
    timeout /t 3 /nobreak >nul

    :: Keep retrying the copy until the file is unlocked (max 15s)
    set RETRY=0
    :copy_loop
        copy /Y "dist\%EXE_NAME%.exe" "%TARGET_EXE%" >nul 2>&1
        if not errorlevel 1 goto copy_done
        set /a RETRY+=1
        if !RETRY! geq 15 (
            echo  [ERROR] Could not replace running .exe after 15 attempts.
            pause
            exit /b 1
        )
        timeout /t 1 /nobreak >nul
        goto copy_loop
    :copy_done
    echo  Replaced: %TARGET_EXE%
) else (
    :: Fresh install: copy to script directory
    copy /Y "dist\%EXE_NAME%.exe" "%SCRIPT_DIR%%EXE_NAME%.exe" >nul
    echo  Copied to: %SCRIPT_DIR%%EXE_NAME%.exe
    set TARGET_EXE=%SCRIPT_DIR%%EXE_NAME%.exe
)

:: ── 8. Create folder structure in destination dir ────────────────────────────
echo [7/9] Setting up folder structure...
set DEST_DIR=%~dp0%TARGET_EXE%
:: Resolve destination folder from exe path
for %%i in ("%TARGET_EXE%") do set DEST_DIR=%%~dpi

if not exist "%DEST_DIR%plugins"  mkdir "%DEST_DIR%plugins"
if not exist "%DEST_DIR%assets"   mkdir "%DEST_DIR%assets"
echo  Created: plugins\  assets\

:: ── 9. Download assets ────────────────────────────────────────────────────────
echo [8/9] Checking assets...
set LOGO=%DEST_DIR%assets\logo.png

if not exist "%LOGO%" (
    echo  Downloading logo.png...
    powershell -NoProfile -Command ^
        "Invoke-WebRequest -Uri 'https://cdn.discordapp.com/attachments/1341185707615719495/1481822728020295760/S7nWcFz.png' -OutFile '%LOGO%' -UseBasicParsing" >nul 2>&1
    if exist "%LOGO%" (echo  logo.png downloaded.) else (echo  Warning: logo.png download failed.)
) else (
    echo  logo.png already present.
)

:: Copy example plugin if it doesn't exist yet
if not exist "%DEST_DIR%plugins\example_plugin.py" (
    if exist "plugins\example_plugin.py" (
        copy "plugins\example_plugin.py" "%DEST_DIR%plugins\example_plugin.py" >nul
        echo  Copied example_plugin.py to plugins\
    )
)

:: ── 10. Clean up temp folder ──────────────────────────────────────────────────
echo [9/9] Cleaning up temp files...
cd /d "%SCRIPT_DIR%"
rmdir /s /q "%BUILD_DIR%"
echo  Removed: %BUILD_DIR%

echo.
echo  ==========================================
echo   Build complete!
echo   Executable : %TARGET_EXE%
echo   Commit SHA : %COMMIT_SHA%
echo  ==========================================
echo.

:: ── 11. Restart (update mode only) ───────────────────────────────────────────
if "%UPDATE_MODE%"=="1" (
    echo  Restarting %EXE_NAME%...
    timeout /t 1 /nobreak >nul
    start "" "%TARGET_EXE%"
    echo  Done.
    exit /b 0
)

:: In fresh-build mode: offer to run immediately
echo  Press any key to launch %EXE_NAME%, or close this window.
pause >nul
start "" "%TARGET_EXE%"
exit /b 0
