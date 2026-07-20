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
docker compose up -d --no-build postgres redis minio model-runtime
if errorlevel 1 (
    echo.
    echo Infrastructure start failed.
    exit /b 1
)

echo.
echo Recreating API, worker and scheduler to pick up backend code changes...
docker compose up -d --no-build --no-deps --force-recreate api worker beat
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
call :verify_stack
if errorlevel 1 exit /b 1
docker compose ps
goto end

:cached_rebuild
echo Rebuilding local application images with Docker cache...
docker compose build api worker beat frontend model-runtime
if errorlevel 1 (
    echo.
    echo Build failed. Application was not restarted.
    exit /b 1
)

echo.
echo Restarting rebuilt application containers...
docker compose up -d --no-deps model-runtime
if errorlevel 1 (
    echo.
    echo Model runtime restart failed.
    exit /b 1
)

docker compose up -d --no-deps api worker beat
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
call :verify_stack
if errorlevel 1 exit /b 1
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
call :verify_stack
if errorlevel 1 exit /b 1
docker compose ps
goto end

:verify_stack
echo Verifying API, frontend, worker and scheduler...
powershell -NoProfile -Command "$ok=$false; for($i=0; $i -lt 30; $i++){ try { $api=Invoke-WebRequest -UseBasicParsing http://localhost:8000/health -TimeoutSec 2; $ui=Invoke-WebRequest -UseBasicParsing http://localhost:5173 -TimeoutSec 2; $worker=(docker inspect -f '{{.State.Running}}' ml-app-worker-1) -eq 'true'; $beat=(docker inspect -f '{{.State.Running}}' ml-app-beat-1) -eq 'true'; if($api.StatusCode -eq 200 -and $ui.StatusCode -eq 200 -and $worker -and $beat){ $ok=$true; break } } catch {}; Start-Sleep -Seconds 1 }; if(-not $ok){ exit 1 }"
if errorlevel 1 (
    echo.
    echo API, frontend, worker or scheduler health verification failed.
    exit /b 1
)
exit /b 0

:help
echo Usage:
echo   rebuild-run.bat          Fast refresh, no image rebuild
echo   rebuild-run.bat build    Rebuild app images with Docker cache
echo   rebuild-run.bat full     Rebuild everything without Docker cache
goto end

:end
endlocal
