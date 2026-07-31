@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

set "TASK_NAME=LonaciScraperQuotidien"
set "SCRIPT_PATH=F:\Startup\Lonaci\run_daily_scrape.bat"

echo ====================================================
echo Installation de la tache planifiee : %TASK_NAME%
echo Script cible : %SCRIPT_PATH%
echo Declenchement : tous les jours a 23:45
echo ====================================================
echo.

if not exist "%SCRIPT_PATH%" (
    echo [ERREUR] Le script %SCRIPT_PATH% est introuvable.
    echo Verifie le chemin avant de reessayer.
    goto :fin
)

schtasks /create /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc daily /st 23:45 /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Tache "%TASK_NAME%" installee avec succes.
    echo Elle se declenchera tous les jours a 23:45.
) else (
    echo.
    echo [ERREUR] La creation de la tache a echoue (code %ERRORLEVEL%^).
    echo Verifie que tu executes ce script avec des droits suffisants.
)

:fin
echo.
pause
