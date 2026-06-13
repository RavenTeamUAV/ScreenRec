@echo off
REM ==========================================================
REM  Налаштування raptor_hud на Windows: venv + залежності
REM  Запускати з кореня репозиторію (де лежить тека raptor_hud).
REM ==========================================================
setlocal

where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py -3
) else (
    set PY=python
)

echo [1/3] Створення віртуального середовища .venv ...
%PY% -m venv .venv
if errorlevel 1 goto :err

echo [2/3] Оновлення pip ...
call .venv\Scripts\python.exe -m pip install --upgrade pip

echo [3/3] Встановлення залежностей ...
call .venv\Scripts\python.exe -m pip install -r raptor_hud\requirements.txt
if errorlevel 1 goto :err

echo.
echo Готово! Запуск:  run.bat
echo   або:          .venv\Scripts\python.exe -m raptor_hud.main
goto :eof

:err
echo.
echo ПОМИЛКА під час налаштування. Перевірте, що встановлено Python 3.10-3.13.
exit /b 1
