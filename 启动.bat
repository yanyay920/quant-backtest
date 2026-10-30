@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYEXE="
python -c "import flask, pandas, matplotlib" 2>nul && set "PYEXE=python"
if not defined PYEXE py -3 -c "import flask, pandas, matplotlib" 2>nul && set "PYEXE=py -3"
if not defined PYEXE "%USERPROFILE%\miniforge3\envs\quant\python.exe" -c "import flask, pandas, matplotlib" 2>nul && set "PYEXE=%USERPROFILE%\miniforge3\envs\quant\python.exe"

if not defined PYEXE (
    echo 未找到安装了 flask、pandas、matplotlib 的 Python 环境。
    echo 请先按 README 安装依赖。
    pause
    exit /b 1
)

echo 使用 Python: %PYEXE%
echo 正在启动绩效报告页，浏览器将自动打开 http://127.0.0.1:5000
start "" /min cmd /c "timeout /t 2 /nobreak >nul & start """" http://127.0.0.1:5000"
%PYEXE% app.py
pause
