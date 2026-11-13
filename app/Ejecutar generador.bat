@echo off
rem Arranca la linea de ensamble (doble clic). Escribe en Supabase.
rem Acepta los mismos argumentos que el generador, por ejemplo:
rem   Ejecutar generador.bat --flujos 20
rem   Ejecutar generador.bat --sin-db
cd /d "%~dp0"
title Linea de ensamble
echo ============================================
echo  LINEA DE ENSAMBLE - generador de datos
echo  Ctrl+C para detener
echo ============================================
echo.
python app\generador_datos.py %*
echo.
echo Fin del programa. Presione una tecla para cerrar.
pause > nul
