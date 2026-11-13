@echo off
rem Pruebas automaticas del repositorio (doble clic).
rem No usan la base de datos ni el .exe: corren con Python.
cd /d "%~dp0"
title Pruebas - Salon106
echo ============================================
echo  PRUEBAS DEL PIPELINE
echo ============================================
python -m pytest tests -q
echo.
if %ERRORLEVEL%==0 (
    echo ============================================
    echo  RESULTADO: todas las pruebas pasaron
    echo ============================================
) else (
    echo ============================================
    echo  RESULTADO: alguna prueba fallo
    echo ============================================
)
pause
