@echo off
setlocal EnableDelayedExpansion

set "REPO_URL=https://github.com/gustaslaoq/Sols-RNG-Sniper.git"
set "EXE_NAME=SlaoqSniper"
set "LOGO_URL=https://raw.githubusercontent.com/gustaslaoq/Sols-RNG-Sniper/main/assets/logo.png"
set "COMMIT_SHA=unknown"
set "UPDATE_MODE=0"
set "TARGET_EXE="
set "SCRIPT_DIR=%~dp0"
set "BUILD_DIR=%TEMP%\SnipeBuild"
set "PS1_FILE=%TEMP%\sniper_stamp.ps1"

if /i "%~1"=="--update" (
    set "UPDATE_MODE=1"
    set "TARGET_EXE=%~2"
)
if "%TARGET_EXE%"=="" set "TARGET_EXE=%SCRIPT_DIR%%EXE_NAME%.exe"

echo.
echo  ==========================================
echo   Slaoq's Sniper - Build Pipeline
echo  ==========================================
echo  Output : %TARGET_EXE%
echo  ==========================================
echo.

echo [1/9] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from https://python.org
    echo  Tick "Add Python to PATH" during install.
    goto die
)
python --version
echo  OK

echo [2/9] Checking Git...
where git >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Git not found. Install from https://git-scm.com
    goto die
)
git --version
echo  OK

echo [3/9] Preparing temp directory...
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
mkdir "%BUILD_DIR%"
if errorlevel 1 ( echo  [ERROR] Cannot create %BUILD_DIR% & goto die )
echo  OK  %BUILD_DIR%

echo [4/9] Cloning repository...
echo  URL: %REPO_URL%
echo.
git clone --depth=1 "%REPO_URL%" "%BUILD_DIR%"
echo.
if errorlevel 1 ( echo  [ERROR] git clone failed & goto die )
echo  OK  Cloned

echo [5/9] Stamping build SHA...
cd /d "%BUILD_DIR%"
for /f %%h in ('git rev-parse --short HEAD 2^>nul') do set COMMIT_SHA=%%h
echo  Commit: %COMMIT_SHA%

if exist "%PS1_FILE%" del "%PS1_FILE%"
echo $sha = "%COMMIT_SHA%"                                                              > "%PS1_FILE%"
echo $file = 'main.py'                                                                 >> "%PS1_FILE%"
echo $content = Get-Content $file -Raw -Encoding UTF8                                  >> "%PS1_FILE%"
echo $marker = 'class AutoUpdater(QObject):'                                           >> "%PS1_FILE%"
echo $newline = [System.Environment]::NewLine                                          >> "%PS1_FILE%"
echo $insert = 'class AutoUpdater(QObject):' + $newline + '    _BUILT_SHA = ' + [char]39 + $sha + [char]39  >> "%PS1_FILE%"
echo if ($content -notmatch '_BUILT_SHA') {                                            >> "%PS1_FILE%"
echo     $content = $content -replace [regex]::Escape($marker), $insert                >> "%PS1_FILE%"
echo }                                                                                  >> "%PS1_FILE%"
echo Set-Content $file $content -Encoding UTF8 -NoNewline                              >> "%PS1_FILE%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1_FILE%"
del "%PS1_FILE%" >nul 2>&1
echo  OK

echo [6/9] Installing dependencies...
python -m pip install --upgrade pip --quiet
python -m pip install pyinstaller PySide6 psutil keyboard aiohttp Pillow --quiet
if errorlevel 1 ( echo  [ERROR] pip install failed & goto die )
echo  OK

echo [7/9] Downloading assets...
if not exist "assets" mkdir "assets"
if not exist "assets\logo.png" (
    echo  Downloading logo.png...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%LOGO_URL%' -OutFile 'assets\logo.png' -UseBasicParsing"
)
if exist "assets\logo.png" (
    echo  Generating app.ico...
    python -c "from PIL import Image; img=Image.open('assets/logo.png').convert('RGBA'); img.save('assets/app.ico',format='ICO',sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
)
echo  OK

echo [8/9] Building .exe (1-3 min)...
echo.
set "ICON_ARG="
if exist "assets\app.ico" set "ICON_ARG=--icon=assets\app.ico"
pyinstaller --onefile --windowed --name %EXE_NAME% --add-data "sniper_engine.py;." --noconfirm --clean %ICON_ARG% main.py
echo.
if errorlevel 1 ( echo  [ERROR] PyInstaller failed & goto die )
if not exist "dist\%EXE_NAME%.exe" ( echo  [ERROR] .exe not found after build & goto die )
echo  OK  .exe built

echo [9/9] Installing...
if "%UPDATE_MODE%"=="1" (
    echo  Waiting for old process to fully exit...
    timeout /t 6 /nobreak >nul
    set RETRY=0
    :copy_retry
    copy /Y "dist\%EXE_NAME%.exe" "%TARGET_EXE%" >nul 2>&1
    if not errorlevel 1 goto copy_ok
    set /a RETRY+=1
    if !RETRY! geq 20 ( echo  [ERROR] Cannot replace exe after 20 attempts & goto die )
    timeout /t 1 /nobreak >nul
    goto copy_retry
    :copy_ok
    echo  OK  Replaced old exe
) else (
    copy /Y "dist\%EXE_NAME%.exe" "%TARGET_EXE%" >nul
    if errorlevel 1 ( echo  [ERROR] Copy failed & goto die )
    echo  OK  Copied to %TARGET_EXE%
)
for %%i in ("%TARGET_EXE%") do set "DEST_DIR=%%~dpi"

echo  Finalizing...
ie4uinit.exe -ClearIconCache >nul 2>&1
ie4uinit.exe -show >nul 2>&1
if not exist "%DEST_DIR%plugins"  mkdir "%DEST_DIR%plugins"
if not exist "%DEST_DIR%assets"   mkdir "%DEST_DIR%assets"
if exist "%BUILD_DIR%\assets\logo.png" copy /Y "%BUILD_DIR%\assets\logo.png" "%DEST_DIR%assets\logo.png" >nul
if exist "%BUILD_DIR%\assets\app.ico"  copy /Y "%BUILD_DIR%\assets\app.ico"  "%DEST_DIR%assets\app.ico"  >nul
if not exist "%DEST_DIR%plugins\example_plugin.py" (
    if exist "%BUILD_DIR%\plugins\example_plugin.py" (
        copy "%BUILD_DIR%\plugins\example_plugin.py" "%DEST_DIR%plugins\example_plugin.py" >nul
    )
)

echo %COMMIT_SHA%> "%DEST_DIR%version.txt"
echo  Wrote version.txt: %COMMIT_SHA%

cd /d "%SCRIPT_DIR%"
rmdir /s /q "%BUILD_DIR%" >nul 2>&1

echo.
echo  ==========================================
echo   BUILD COMPLETE  ^|  Commit: %COMMIT_SHA%
echo   Output: %TARGET_EXE%
echo  ==========================================
echo.

if "%UPDATE_MODE%"=="1" (
    echo.
    echo  Waiting for old process to fully exit...
    set MAX_WAIT=30
    set WAITED=0
    :wait_exit
    tasklist /FI "IMAGENAME eq %EXE_NAME%.exe" 2>nul | find /I "%EXE_NAME%.exe" >nul 2>&1
    if not errorlevel 1 (
        set /a WAITED+=1
        if !WAITED! geq !MAX_WAIT! goto launch_anyway
        timeout /t 1 /nobreak >nul
        goto wait_exit
    )
    :launch_anyway
    echo  Old process exited ^(waited !WAITED!s^). Launching new version...
    timeout /t 2 /nobreak >nul
    echo.
    echo  ==========================================
    echo   Update complete! Starting new version...
    echo  ==========================================
    echo.
    start "" "%TARGET_EXE%"
    exit /b 0
)

echo  Press any key to launch...
pause >nul
start "" "%TARGET_EXE%"
exit /b 0

:die
echo.
echo  ==========================================
echo   BUILD FAILED
echo  ==========================================
echo.
pause
exit /b 1
