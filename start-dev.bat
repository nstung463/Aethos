@echo off
setlocal enabledelayedexpansion

echo Aethos Docker Startup
echo ===================

if not exist .env (
    echo .env not found. Creating from .env.example...
    copy .env.example .env
    echo Please edit .env with your API keys, then run again.
    pause
    exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
    echo Docker not found. Install Docker Desktop first.
    pause
    exit /b 1
)

docker compose version >nul 2>nul
if errorlevel 1 (
    echo Docker Compose v2 not found. Please update Docker Desktop.
    pause
    exit /b 1
)

echo Configuration looks good.
echo.

echo Building and starting services...
docker compose up -d --build
if errorlevel 1 (
    echo Failed to start Docker services.
    pause
    exit /b 1
)

echo.
echo Waiting for services to become healthy...
timeout /t 10 /nobreak >nul

echo.
echo Health checks

curl -fsS http://localhost:8080/v1/models >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Backend: http://localhost:8080
) else (
    echo   [OK]   Backend: http://localhost:8080
)

curl -fsS http://localhost:3000 >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Frontend: http://localhost:3000
) else (
    echo   [OK]   Frontend: http://localhost:3000
)

echo.
echo Startup complete.
echo.
echo Open http://localhost:3000 in your browser.
echo.
echo Useful commands
echo   docker compose ps
echo   docker compose logs -f aethos-backend
echo   docker compose logs -f aethos-frontend
echo   docker compose down
echo.
pause
