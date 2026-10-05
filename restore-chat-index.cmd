@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "STORE=%APPDATA%\Code\User\workspaceStorage\a45496d02d5f973f532c881076b0d01d"
set "LOG=%~dp0restore-chat-index.log"

REM Tee everything to console AND %LOG% via a sub-shell that pipes through powershell.
REM (cmd has no native tee, but invoking the body recursively + piping works.)
if /I not "%~1"=="__inner" (
    echo Logging to: %LOG%
    > "%LOG%" echo === restore-chat-index.cmd run on %DATE% %TIME% ===
    call "%~f0" __inner 2>&1 | powershell -NoLogo -NoProfile -Command "$input | Tee-Object -FilePath '%LOG%' -Append"
    echo.
    echo Full log written to: %LOG%
    echo Press any key to close this window . . .
    pause >nul
    exit /b
)

echo.
echo === Rebuild chat session index from chatSessions\*.jsonl ===
echo.

tasklist /FI "IMAGENAME eq Code.exe" 2>nul | find /I "Code.exe" >nul
if not errorlevel 1 (
    echo.
    echo ###############################################################
    echo # ERROR: VS Code ^(Code.exe^) is still running.                  #
    echo # Close ALL VS Code windows ^(check the system tray too^)       #
    echo # and run this script again.                                   #
    echo ###############################################################
    exit /b 1
)

if not exist "%STORE%\state.vscdb" (
    echo ERROR: state.vscdb not found at %STORE%
    exit /b 1
)
if not exist "%STORE%\chatSessions" (
    echo ERROR: chatSessions folder not found at %STORE%
    exit /b 1
)

REM Interpreter lives OUTSIDE OneDrive (avoids sync corrupting the venv / an
REM in-repo .venv OneDrive flags for cert issues). Keep in sync with
REM .vscode\settings.json python.defaultInterpreterPath.
set "PY=%USERPROFILE%\.virtualenvs\mcp-fishing\Scripts\python.exe"
if not exist "%PY%" (
    echo ERROR: venv python not found at %PY%
    echo Create it once with:
    echo   py -3.12 -m venv "%USERPROFILE%\.virtualenvs\mcp-fishing"
    echo   "%USERPROFILE%\.virtualenvs\mcp-fishing\Scripts\python.exe" -m pip install -e .
    exit /b 1
)

"%PY%" "%~dp0restore-chat-index.py" "%STORE%"
if errorlevel 1 (
    echo.
    echo ###############################################################
    echo # SCRIPT FAILED. See output above and %LOG%.
    echo ###############################################################
    exit /b 1
)

echo.
echo ###############################################################
echo # SUCCESS. Reopen the workspace in VS Code; the chat history   #
echo # dropdown should now list all prior sessions.                 #
echo ###############################################################
exit /b 0
