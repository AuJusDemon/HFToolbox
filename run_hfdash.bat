@echo off
setlocal enabledelayedexpansion
title HFToolbox - Manager

:: ══════════════════════════════════════════════════════════════════════════════
::  HFToolbox Manager
::  Starts Caddy (reverse proxy) and the FastAPI backend, with auto-restart
::  on crash and crash-rate limiting so a boot loop doesn't spin forever.
::
::  Usage: double-click this file, or run from a terminal.
::  To stop: close this window. Caddy keeps running separately — kill it with:
::           taskkill /im caddy.exe /f
:: ══════════════════════════════════════════════════════════════════════════════

:: ── Config ────────────────────────────────────────────────────────────────────
:: All paths are relative to this file — move the project anywhere, still works.
set ROOT=%~dp0
set BACKEND_DIR=%ROOT%backend
set LOG_DIR=%ROOT%logs

:: Python: tries 'py' (Windows Python Launcher) first, falls back to 'python'
set PYTHON=py
where py >nul 2>&1 || set PYTHON=python

:: Caddy dir — override by setting CADDY_DIR as a system/user env var before
:: running this script, or just change the default below.
if not defined CADDY_DIR set CADDY_DIR=C:\caddy

:: Restart loop tuning
set MAX_CRASHES_BEFORE_WAIT=5
set CRASH_WINDOW_SECS=120
set LONG_WAIT_SECS=30

:: ── Setup ─────────────────────────────────────────────────────────────────────
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo.
echo  ================================================================
echo   HFToolbox
echo   Backend   : %BACKEND_DIR%
echo   Python    : %PYTHON%
echo   Caddy     : %CADDY_DIR%
echo   Logs      : %LOG_DIR%
echo  ================================================================
echo.

:: ── Preflight checks ──────────────────────────────────────────────────────────
where %PYTHON% >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install from https://python.org and ensure
    echo         it is in your PATH, then try again.
    pause
    exit /b 1
)

if not exist "%CADDY_DIR%\caddy.exe" (
    echo [WARN] caddy.exe not found at %CADDY_DIR%\caddy.exe
    echo        Set the CADDY_DIR environment variable or edit this file.
    echo        Continuing without Caddy — you will need to start it manually.
    echo.
)

if not exist "%BACKEND_DIR%\.env" (
    echo [WARN] No .env found at %BACKEND_DIR%\.env
    echo        Copy .env.example to .env and fill in your credentials.
    echo        Server will start but OAuth login will not work.
    echo.
)

:: ── Record git commit hash ────────────────────────────────────────────────────
:: Writes deploy_info.json so /health and /health/integrity can report exactly
:: which commit is running. Compare against the public GitHub repo to verify.
where git >nul 2>&1
if %errorlevel% equ 0 (
    for /f %%i in ('git -C "%ROOT%." rev-parse HEAD 2^>nul') do set GIT_HASH=%%i
    for /f %%i in ('git -C "%ROOT%." rev-parse --short HEAD 2^>nul') do set GIT_SHORT=%%i
)
if not defined GIT_HASH set GIT_HASH=unknown
if not defined GIT_SHORT set GIT_SHORT=unknown

(echo {"commit": "!GIT_HASH!", "commit_short": "!GIT_SHORT!", "deployed_at": "%DATE% %TIME%"}) > "%BACKEND_DIR%\deploy_info.json"
echo [%DATE% %TIME%] Commit !GIT_SHORT! >> "%LOG_DIR%\manager.log"

if "!GIT_SHORT!" == "unknown" (
    echo [INFO] Git not available or not a repo — commit hash will show as unknown
) else (
    echo [INFO] Commit: !GIT_SHORT! ^(!GIT_HASH!^)
)
echo.

:: ── Start Caddy ───────────────────────────────────────────────────────────────
if exist "%CADDY_DIR%\caddy.exe" (
    tasklist /fi "imagename eq caddy.exe" 2>nul | find /i "caddy.exe" >nul
    if %errorlevel% neq 0 (
        echo [%DATE% %TIME%] Starting Caddy...
        start "HFToolbox - Caddy" /D "%CADDY_DIR%" caddy.exe run --config Caddyfile
        echo [%DATE% %TIME%] Caddy started >> "%LOG_DIR%\manager.log"
    ) else (
        echo [%DATE% %TIME%] Caddy already running
    )
)

echo.
echo [INFO] Starting backend. Close this window to stop.
echo.

:: ── Backend restart loop ──────────────────────────────────────────────────────
set CRASH_COUNT=0
:: Seed far in the past so the very first start never counts as a crash
set LAST_CRASH_TIME=-9999

:backend_loop

:: Revive Caddy if it died
if exist "%CADDY_DIR%\caddy.exe" (
    tasklist /fi "imagename eq caddy.exe" 2>nul | find /i "caddy.exe" >nul
    if %errorlevel% neq 0 (
        echo [%DATE% %TIME%] Caddy died — restarting...
        echo [%DATE% %TIME%] Caddy died, restarting >> "%LOG_DIR%\manager.log"
        start "HFToolbox - Caddy" /D "%CADDY_DIR%" caddy.exe run --config Caddyfile
    )
)

:: Crash-rate detection
for /f "tokens=1-3 delims=:." %%a in ("%TIME%") do set /a NOW_SECS=%%a*3600+%%b*60+%%c
set /a TIME_SINCE_CRASH=%NOW_SECS%-%LAST_CRASH_TIME%
if %TIME_SINCE_CRASH% lss 0 set /a TIME_SINCE_CRASH=%TIME_SINCE_CRASH%+86400

if %TIME_SINCE_CRASH% lss %CRASH_WINDOW_SECS% (
    set /a CRASH_COUNT+=1
) else (
    set CRASH_COUNT=0
)
set LAST_CRASH_TIME=%NOW_SECS%

if %CRASH_COUNT% geq %MAX_CRASHES_BEFORE_WAIT% (
    echo [%DATE% %TIME%] Crashing too fast — waiting %LONG_WAIT_SECS%s before next restart
    echo [%DATE% %TIME%] Crash backoff %LONG_WAIT_SECS%s >> "%LOG_DIR%\manager.log"
    set CRASH_COUNT=0
    timeout /t %LONG_WAIT_SECS% /nobreak >nul
)

echo [%DATE% %TIME%] Starting backend...
echo [%DATE% %TIME%] Starting backend >> "%LOG_DIR%\manager.log"

cd /d "%BACKEND_DIR%"
%PYTHON% -m uvicorn server:app --port 8000 --log-level info

set EXIT_CODE=%errorlevel%
echo [%DATE% %TIME%] Backend exited ^(code %EXIT_CODE%^) — restarting in 3s...
echo [%DATE% %TIME%] Backend exited code=%EXIT_CODE% >> "%LOG_DIR%\manager.log"
timeout /t 3 /nobreak >nul
goto backend_loop
