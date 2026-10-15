@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "CART_PY=python"
if exist "%~dp0.venv\Scripts\python.exe" (
  set "CART_PY="%~dp0.venv\Scripts\python.exe""
) else (
  where py >nul 2>nul
  if not errorlevel 1 set "CART_PY=py -3"
)
set "CART_MODE=%~1"
if not defined CART_MODE (
  echo 1. Drive UI - disconnected by default
  echo 2. Camera / YOLO UI - no motors
  echo 3. Camera + LiDAR - starts sensors, no motors
  echo 4. Sensor demo - no devices
  echo 5. Drive preview - real connection disabled
  echo 6. Training data check - no training
  set /p "CART_MODE=Select: "
)
if "%CART_MODE%"=="1" set "CART_MODE=drive"
if "%CART_MODE%"=="2" set "CART_MODE=camera"
if "%CART_MODE%"=="3" set "CART_MODE=sensors"
if "%CART_MODE%"=="4" set "CART_MODE=demo"
if "%CART_MODE%"=="5" set "CART_MODE=preview"
if "%CART_MODE%"=="6" set "CART_MODE=train-check"
if "%CART_MODE%"=="drive" (
  %CART_PY% -B "%~dp0cart-manual-ui\app.py"
  goto done
)
if "%CART_MODE%"=="preview" (
  %CART_PY% -B "%~dp0cart-manual-ui\app.py" --preview-only
  goto done
)
if "%CART_MODE%"=="camera" (
  %CART_PY% -B "%~dp0cart-target-preview\preview.py"
  goto done
)
if "%CART_MODE%"=="sensors" (
  %CART_PY% -B "%~dp0cart-sensor-check\app.py" --start
  goto done
)
if "%CART_MODE%"=="demo" (
  %CART_PY% -B "%~dp0cart-sensor-check\app.py" --demo
  goto done
)
if "%CART_MODE%"=="timed" (
  %CART_PY% -B "%~dp0cart-manual-ui\timed_app.py"
  goto done
)
if "%CART_MODE%"=="train-init" (
  %CART_PY% -B "%~dp0gray-panel-training\train_gray_panel.py" init
  goto done
)
if "%CART_MODE%"=="train-check" (
  %CART_PY% -B "%~dp0gray-panel-training\train_gray_panel.py" check
  goto done
)
echo Unknown mode. See USAGE.md.
exit /b 2
:done
exit /b %errorlevel%
