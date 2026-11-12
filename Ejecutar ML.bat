@echo off
rem Entrena el modelo y muestra las decisiones (doble clic).
rem Los artefactos se guardan en ml\ (ver ML_DIR_ARTEFACTOS).
cd /d "%~dp0"
set "ML_DIR_ARTEFACTOS=ml"
title Modelo de ML
echo ============================================
echo  1. ENTRENAMIENTO DEL MODELO DE RIESGO
echo ============================================
python ml\entrenar_con_supabase.py --tabla v_riesgo_piezas
if errorlevel 1 goto :error

echo.
echo ============================================
echo  2. DETECCION DE ANOMALIAS
echo ============================================
python ml\detectar_anomalias.py

echo.
echo ============================================
echo  3. PREDICCION Y DECISIONES
echo ============================================
python ml\predecir_interactivo.py --ultimas 15
goto :fin

:error
echo.
echo No se pudo entrenar. Revisa la conexion y que existan datos
echo (Ejecutar generador.bat).

:fin
echo.
pause
