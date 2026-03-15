@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  Slaoq's Sniper - Build & Deploy Script
::
::  Modes:
::    build.bat              -> fresh build into current folder
::    build.bat --update "C:\path\to\SlaoqSniper.exe"
::                           -> rebuild + replace .exe + restart
::
::  Steps:
::    1.  Check Python
::    2.  Check Git
::    3.  Check network
::    4.  Prepare temp directory
::    5.  Clone repository  (output fully visible on error)
::    6.  Stamp commit SHA into main.py
::    7.  pip install dependencies
::    8.  PyInstaller --onefile build
::    9.  Copy .exe to destination
::   10.  Create folders + download assets + copy example plugin
::   11.  Cleanup temp folder
::   12.  Restart (--update mode only)
:: ============================================================

:: ---- CONFIGURE THESE ----------------------------------------
set "REPO_URL=https://github.com/gustaslaoq/Sols-RNG-Sniper.git"
set "EXE_NAME=SlaoqSniper"
set "LOGO_URL=https://cdn.discordapp.com/attachments/1341185707615719495/1481822728020295760/S7nWcFz.png"
:: -------------------------------------------------------------

set "UPDATE_MODE=0"
set "TARGET_EXE="
set "SCRIPT_DIR=%~dp0"

if /i "%~1"=="--update" (
    set "UPDATE_MODE=1"
    set "TARGET_EXE=%~2"
)
if "%TARGET_EXE%"=="" set "TARGET_EXE=%SCRIPT_DIR%%EXE_NAME%.exe"

:: Fixed temp path avoids %RANDOM% collision
set "BUILD_DIR=%TEMP%\SnipeBuild"

echo.
echo  ==========================================
echo   Slaoq's Sniper - Build Pipeline
echo  ==========================================
echo  Repo    : %REPO_URL%
echo  Output  : %TARGET_EXE%
echo  TempDir : %BUILD_DIR%
echo  ==========================================
echo.

:: ---- STEP 1  Check Python -----------------------------------
echo [1/11] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python not found in PATH.
    echo  Install Python 3.10+ from https://python.org
    echo  Tick "Add Python to PATH" during install.
    echo.
    pause & exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo  OK  Python %PY_VER%

:: ---- STEP 2  Check Git --------------------------------------
echo [2/11] Checking Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Git not found in PATH.
    echo  Install Git from https://git-scm.com and rerun.
    echo.
    pause & exit /b 1
)
for /f "tokens=3 delims= " %%v in ('git --version 2^>^&1') do set "GIT_VER=%%v"
echo  OK  Git %GIT_VER%

:: ---- STEP 3  Check network ----------------------------------
echo [3/11] Checking network...
ping -n 1 github.com >nul 2>&1
if errorlevel 1 (
    echo  [WARN] ping github.com failed (firewall may block ICMP). Continuing...
) else (
    echo  OK  github.com reachable
)

:: ---- STEP 4  Prepare temp directory ------------------------
echo [4/11] Preparing build directory...
if exist "%BUILD_DIR%" (
    echo  Removing old build dir...
    rmdir /s /q "%BUILD_DIR%"
    if exist "%BUILD_DIR%" (
        echo  [ERROR] Could not delete %BUILD_DIR%
        echo  Close any Explorer windows pointing there and retry.
        pause & exit /b 1
    )
)
mkdir "%BUILD_DIR%"
echo  OK  %BUILD_DIR% ready

:: ---- STEP 5  Clone repository (NO output suppression) ------
echo [5/11] Cloning repository...
echo  Running: git clone --depth=1 %REPO_URL% "%BUILD_DIR%"
echo.

git clone --depth=1 "%REPO_URL%" "%BUILD_DIR%"
set "GIT_EXITCODE=%errorlevel%"

echo.
if %GIT_EXITCODE% neq 0 (
    echo  ============================================================
    echo  [ERROR] git clone FAILED  ^(exit code %GIT_EXITCODE%^)
    echo  ============================================================
    echo.
    echo  Common fixes:
    echo.
    echo  1. Wrong URL - current value in this script:
    echo     %REPO_URL%
    echo     Edit the REPO_URL line at the top of build.bat if needed.
    echo.
    echo  2. Private repo - add a Personal Access Token:
    echo     https://TOKEN@github.com/user/repo.git
    echo.
    echo  3. GitHub auth - run this once in a terminal to cache credentials:
    echo     git clone %REPO_URL% "%TEMP%\test_clone"
    echo     Accept the login prompt, then delete %TEMP%\test_clone
    echo.
    echo  4. TLS issues - try running:
    echo     git config --global http.sslVerify false
    echo.
    echo  5. Antivirus - temporarily disable real-time protection.
    echo  ============================================================
    pause & exit /b 1
)
echo  OK  Cloned

:: ---- STEP 6  Stamp commit SHA --------------------------------
echo [6/11] Stamping build info...
cd /d "%BUILD_DIR%"

set "COMMIT_SHA=unknown"
for /f %%h in ('git rev-parse --short HEAD 2^>nul') do set "COMMIT_SHA=%%h"
echo  Commit: %COMMIT_SHA%

:: Insert _BUILT_SHA into the AutoUpdater class in main.py
powershell -NoProfile -Command ^
  "$file = 'main.py';" ^
  "$txt  = Get-Content $file -Raw -Encoding UTF8;" ^
  "$mark = 'class AutoUpdater(QObject):';" ^
  "$repl = 'class AutoUpdater(QObject):`r`n    _BUILT_SHA = \"%COMMIT_SHA%\"';" ^
  "if ($txt -notmatch '_BUILT_SHA') { $txt = $txt -replace [regex]::Escape($mark), $repl };" ^
  "Set-Content $file $txt -Encoding UTF8 -NoNewline;" ^
  "Write-Host '  SHA stamped OK'"
if errorlevel 1 echo  [WARN] SHA stamp failed - build continues anyway

:: ---- STEP 7  Install dependencies ---------------------------
echo [7/11] Installing Python dependencies...
python -m pip install --upgrade pip --quiet --disable-pip-version-check
python -m pip install pyinstaller PySide6 psutil keyboard aiohttp ^
    --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo  [ERROR] pip install failed. Try manually:
    echo    pip install pyinstaller PySide6 psutil keyboard aiohttp
    echo.
    pause & exit /b 1
)
echo  OK  Dependencies installed

:: ---- STEP 8  PyInstaller build ------------------------------
echo [8/11] Building .exe with PyInstaller (this takes 1-3 min)...
echo.

set "ICON_OPT="
if exist "assets\app.ico" set "ICON_OPT=--icon=assets\app.ico"

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "%EXE_NAME%" ^
    --add-data "sniper_engine.py;." ^
    %ICON_OPT% ^
    --noconfirm ^
    --clean ^
    main.py

echo.
if errorlevel 1 (
    echo  [ERROR] PyInstaller failed. Read the output above for details.
    pause & exit /b 1
)
if not exist "dist\%EXE_NAME%.exe" (
    echo  [ERROR] dist\%EXE_NAME%.exe not found after build.
    pause & exit /b 1
)
echo  OK  dist\%EXE_NAME%.exe created

:: ---- STEP 9  Copy .exe to destination ----------------------
echo [9/11] Deploying executable...

if "%UPDATE_MODE%"=="1" (
    echo  Waiting 3s for old process to release file lock...
    timeout /t 3 /nobreak >nul
    set "RETRY=0"
    :copy_retry
        copy /Y "dist\%EXE_NAME%.exe" "%TARGET_EXE%" >nul 2>&1
        if not errorlevel 1 goto copy_ok
        set /a RETRY+=1
        if !RETRY! geq 20 (
            echo  [ERROR] Could not replace %TARGET_EXE% after 20 attempts.
            pause & exit /b 1
        )
        echo  File locked, retrying !RETRY!/20...
        timeout /t 1 /nobreak >nul
        goto copy_retry
    :copy_ok
    echo  OK  Replaced: %TARGET_EXE%
) else (
    copy /Y "dist\%EXE_NAME%.exe" "%TARGET_EXE%" >nul
    if errorlevel 1 (
        echo  [ERROR] Copy to %TARGET_EXE% failed.
        pause & exit /b 1
    )
    echo  OK  Copied to: %TARGET_EXE%
)

for %%i in ("%TARGET_EXE%") do set "DEST_DIR=%%~dpi"

:: ---- STEP 10  Folders + assets + plugins -------------------
echo [10/11] Setting up folders and assets...

if not exist "%DEST_DIR%plugins" mkdir "%DEST_DIR%plugins"
if not exist "%DEST_DIR%assets"  mkdir "%DEST_DIR%assets"
echo  OK  plugins\  assets\  created

:: Download logo.png
if not exist "%DEST_DIR%assets\logo.png" (
    echo  Downloading logo.png...
    powershell -NoProfile -Command ^
      "try { Invoke-WebRequest -Uri '%LOGO_URL%' -OutFile '%DEST_DIR%assets\logo.png' -UseBasicParsing; Write-Host '  OK  logo.png saved' } catch { Write-Host '  [WARN] logo.png download failed:' $_.Exception.Message }"
) else (
    echo  OK  logo.png already present
)

:: Copy example plugin
if not exist "%DEST_DIR%plugins\example_plugin.py" (
    if exist "%BUILD_DIR%\plugins\example_plugin.py" (
        copy "%BUILD_DIR%\plugins\example_plugin.py" ^
             "%DEST_DIR%plugins\example_plugin.py" >nul
        echo  OK  example_plugin.py copied
    )
)

:: ---- STEP 11  Cleanup --------------------------------------
echo [11/11] Cleaning up temp files...
cd /d "%SCRIPT_DIR%"
rmdir /s /q "%BUILD_DIR%" >nul 2>&1
if exist "%BUILD_DIR%" (
    echo  [WARN] Temp dir not fully removed: %BUILD_DIR%
) else (
    echo  OK  Temp folder removed
)

:: ---- DONE --------------------------------------------------
echo.
echo  ==========================================
echo   Build COMPLETE
echo   Executable : %TARGET_EXE%
echo   Commit     : %COMMIT_SHA%
echo  ==========================================
echo.

if "%UPDATE_MODE%"=="1" (
    echo  Restarting %EXE_NAME%...
    timeout /t 1 /nobreak >nul
    start "" "%TARGET_EXE%"
    exit /b 0
)

echo  Press any key to launch %EXE_NAME%...
pause >nul
start "" "%TARGET_EXE%"
exit /b 0
