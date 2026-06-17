@echo off
setlocal

cd /d "%~dp0"

if /i "%~1"=="full" goto full_rebuild
if /i "%~1"=="--full" goto full_rebuild
if /i "%~1"=="build" goto cached_rebuild
if /i "%~1"=="--build" goto cached_rebuild
if /i "%~1"=="help" goto help
if /i "%~1"=="--help" goto help

echo Refreshing application containers without rebuilding images...
docker compose up -d --no-build postgres redis minio
if errorlevel 1 (
    echo.
    echo Infrastructure start failed.
    exit /b 1
)

echo.
echo Recreating API and worker to pick up backend code changes...
docker compose up -d --no-build --no-deps --force-recreate api worker
if errorlevel 1 (
    echo.
    echo Application refresh failed.
    exit /b 1
)

echo.
echo Recreating frontend to clear Vite transform cache...
docker compose up -d --no-build --no-deps --force-recreate frontend
if errorlevel 1 (
    echo.
    echo Application refresh failed.
    exit /b 1
)

echo.
docker compose ps
goto end

:cached_rebuild
echo Rebuilding local application images with Docker cache...
docker compose build api worker frontend
if errorlevel 1 (
    echo.
    echo Build failed. Application was not restarted.
    exit /b 1
)

echo.
echo Restarting rebuilt application containers...
docker compose up -d --no-deps api worker
if errorlevel 1 (
    echo.
    echo Restart failed.
    exit /b 1
)

echo.
echo Recreating rebuilt frontend...
docker compose up -d --no-deps --force-recreate frontend
if errorlevel 1 (
    echo.
    echo Restart failed.
    exit /b 1
)

echo.
docker compose ps
goto end

:full_rebuild
echo Rebuilding all Docker images without cache...
docker compose build --no-cache
if errorlevel 1 (
    echo.
    echo Build failed. Application was not restarted.
    exit /b 1
)

echo.
echo Restarting the full stack...
docker compose up -d --force-recreate --remove-orphans
if errorlevel 1 (
    echo.
    echo Restart failed.
    exit /b 1
)

echo.
docker compose ps
goto end

:help
echo Usage:
echo   rebuild-run.bat          Fast refresh, no image rebuild
echo   rebuild-run.bat build    Rebuild app images with Docker cache
echo   rebuild-run.bat full     Rebuild everything without Docker cache
goto end

:end
endlocal
