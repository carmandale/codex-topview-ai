@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ==========================================
echo   Social media video upload tool - One click installation (Windows)
echo ==========================================
echo.

REM ---------- Check Python ----------
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [mistake] not found python，Please install first Python 3.9+
    echo    Download address: https://www.python.org/downloads/
    echo    Please check when installing "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_VERSION=%%i
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.version_info.major)"') do set PY_MAJOR=%%i
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.version_info.minor)"') do set PY_MINOR=%%i

if %PY_MAJOR% lss 3 (
    echo [mistake] Python version required ^>= 3.9，Currently %PY_VERSION%
    pause
    exit /b 1
)
if %PY_MAJOR% equ 3 if %PY_MINOR% lss 9 (
    echo [mistake] Python version required ^>= 3.9，Currently %PY_VERSION%
    pause
    exit /b 1
)
echo [OK] detected Python %PY_VERSION%

REM ---------- Create a virtual environment ----------
if exist ".venv" (
    echo [hint] Found that there is already .venv，Skip creation
) else (
    echo [Install] Create a virtual environment .venv ...
    python -m venv .venv
    echo [OK] Virtual environment created
)

set PIP=.venv\Scripts\pip.exe
set PYTHON_VENV=.venv\Scripts\python.exe

REM ---------- Upgrade pip ----------
echo [Install] upgrade pip / setuptools / wheel ...
if exist "vendor_wheels" (
    %PIP% install --no-index --find-links vendor_wheels --upgrade pip setuptools wheel -q 2>nul
    if %errorlevel% neq 0 (
        %PIP% install --upgrade pip setuptools wheel -q
    )
) else (
    %PIP% install --upgrade pip setuptools wheel -q
)

REM ---------- Install dependencies ----------
echo [Install] Install dependency packages ...
echo [hint] Offline wheel package for macOS Version，Windows Dependencies will be installed from the network
%PIP% install certifi charset-normalizer click cssselect DataRecorder "DownloadKit>=2.0.7" et_xmlfile filelock idna lxml openpyxl packaging psutil requests requests-file "tldextract>=3.4.4" urllib3 websocket-client -q
if %errorlevel% neq 0 (
    echo [mistake] Dependency installation failed, please check the network connection
    pause
    exit /b 1
)
echo [OK] Dependency installation completed

REM ---------- Install local DrissionPage ----------
echo [Install] Install local DrissionPage (v4.1.1.2) ...
%PIP% install "%~dp0DrissionPage" -q
echo [OK] DrissionPage Installed

REM ---------- Install the main project ----------
echo [Install] Install social-uploader CLI ...
%PIP% install -e "%~dp0." -q
echo [OK] social-uploader Installed

REM ---------- verify ----------
echo.
echo ==========================================
echo   Verify installation
echo ==========================================
.venv\Scripts\social-upload.exe --help

echo.
echo ==========================================
echo   Installation completed！
echo ==========================================
echo.
echo Usage：
echo   1. double click start_chrome_debug.bat start up Chrome debug mode
echo   2. Manually log in to the target platform in the browser（TikTok / Instagram / YouTube）
echo   3. Upload video：
echo      .venv\Scripts\social-upload tiktok --video "video.mp4" --title "title" --description "describe"
echo      .venv\Scripts\social-upload instagram --video "video.mp4" --caption "copywriting"
echo      .venv\Scripts\social-upload youtube --video "video.mp4" --title "title" --description "describe"
echo.
pause
