@echo off
setlocal
rem Открывает живой лог агентов в отдельном окне терминала.
where python >nul 2>&1
if errorlevel 1 (
    echo Python не найден в PATH.
    pause
    exit /b 1
)
start "isota agents" cmd /k python "%~dp0agents_console.py"
endlocal
