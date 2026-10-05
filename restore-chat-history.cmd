@echo off
setlocal
set "ROOT=%APPDATA%\Code\User\workspaceStorage"
set "OLD=%ROOT%\6299946135e6ef30c553636fc6391d0f"
set "NEW=%ROOT%\a45496d02d5f973f532c881076b0d01d"
set "STAMP=%RANDOM%"

echo.
echo === Restore prior chat history for OneDrive\MCP Fishing ===
echo.

tasklist /FI "IMAGENAME eq Code.exe" 2>nul | find /I "Code.exe" >nul
if not errorlevel 1 (
    echo ERROR: VS Code ^(Code.exe^) is still running. Close ALL VS Code windows first.
    pause
    exit /b 1
)

if not exist "%OLD%" (
    echo ERROR: Source folder not found: %OLD%
    pause
    exit /b 1
)
if not exist "%NEW%" (
    echo ERROR: Destination folder not found: %NEW%
    pause
    exit /b 1
)

echo Moving aside new (empty) storage:
echo   %NEW%
echo to %NEW%.replaced-%STAMP%
ren "%NEW%" "a45496d02d5f973f532c881076b0d01d.replaced-%STAMP%"
if errorlevel 1 ( echo Rename failed. & pause & exit /b 1 )

echo Renaming old storage to active id:
echo   %OLD%
echo to %NEW%
ren "%OLD%" "a45496d02d5f973f532c881076b0d01d"
if errorlevel 1 ( echo Rename failed. & pause & exit /b 1 )

echo.
echo Done. Reopen the workspace in VS Code; prior chat history should appear in
echo the Chat view history panel.
echo.
echo Rollback if needed:
echo   ren "%NEW%" "6299946135e6ef30c553636fc6391d0f"
echo   ren "%NEW%.replaced-%STAMP%" "a45496d02d5f973f532c881076b0d01d"
echo.
pause
