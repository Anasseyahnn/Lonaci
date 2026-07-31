@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"

rem ============================================================
rem Lonaci - Scrape quotidien + import base de donnees
rem Declenche par Windows Task Scheduler
rem ============================================================

set "PROJECT_DIR=F:\Startup\Lonaci"
set "LOG_DIR=%PROJECT_DIR%\logs"

cd /d "%PROJECT_DIR%" || (
    echo [FATAL] Impossible d'acceder a %PROJECT_DIR% >> "%TEMP%\lonaci_scrape_fatal.log"
    exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

rem Nom de log horodate (date independante de la locale via WMIC)
for /f "usebackq" %%I in (`powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"`) do set "TODAY=%%I"
set "LOG_FILE=%LOG_DIR%\daily_scrape_%TODAY%.log"

set "EXIT_CODE=0"

call :log "===================================================="
call :log "Debut du scrape quotidien - %DATE% %TIME%"
call :log "Dossier de travail: %CD%"
call :log "===================================================="

rem --- Etape 1 : Scraping (Node.js) ---
call :log ""
call :log "[1/2] Lancement du scraper : node backend\scraper\fetch_results.js"
node backend\scraper\fetch_results.js >> "%LOG_FILE%" 2>&1
set "NODE_EXIT=%ERRORLEVEL%"

if not "%NODE_EXIT%"=="0" (
    call :log "[ERREUR] Le scraper a echoue avec le code %NODE_EXIT%. Import de la base annule."
    set "EXIT_CODE=%NODE_EXIT%"
    goto :end
)

call :log "[OK] Scraper termine avec succes."

rem --- Etape 2 : Import + tracker prospectif (Python) ---
call :log ""
call :log "[2/2] Lancement de l'import : python backend\database\db.py"
python backend\database\db.py >> "%LOG_FILE%" 2>&1
set "PYTHON_EXIT=%ERRORLEVEL%"

if not "%PYTHON_EXIT%"=="0" (
    call :log "[ERREUR] L'import/tracker Python a echoue avec le code %PYTHON_EXIT%."
    set "EXIT_CODE=%PYTHON_EXIT%"
    goto :end
)

call :log "[OK] Import et suivi prospectif termines avec succes."

:end
call :log ""
call :log "===================================================="
if "%EXIT_CODE%"=="0" (
    call :log "Scrape quotidien termine SANS ERREUR - %DATE% %TIME%"
) else (
    call :log "Scrape quotidien termine AVEC ERREUR (code %EXIT_CODE%) - %DATE% %TIME%"
)
call :log "===================================================="

exit /b %EXIT_CODE%

:log
if "%~1"=="" (
    echo.
    echo. >> "%LOG_FILE%"
) else (
    echo %~1
    echo %~1 >> "%LOG_FILE%"
)
exit /b 0
