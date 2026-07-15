@echo off
chcp 65001 >nul 2>&1

echo Closing existing Chrome process...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM Try common Chrome installation paths in order of priority
set CHROME_PATH=

if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
    goto :found
)
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    goto :found
)
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
    goto :found
)

echo [mistake] not found Google Chrome，Please specify the path manually or install Chrome
echo    Download address: https://www.google.com/chrome/
pause
exit /b 1

:found
echo Starting in debug mode Google Chrome (port 9222)...
start "" "%CHROME_PATH%" --remote-debugging-port=9222 --restore-last-session

echo Started successfully! Now you can run the automation script。
echo.
echo If this is the first time you use it, please log in to the target platform in the browser first：
echo   - TikTok: https://www.tiktok.com
echo   - Instagram: https://www.instagram.com
echo   - YouTube: https://studio.youtube.com
echo.
pause
