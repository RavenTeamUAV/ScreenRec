@echo off
REM Запуск raptor_hud на Windows. Аргументи передаються далі.
REM   run_windows.bat
REM   run_windows.bat --mavlink udpin:0.0.0.0:14550 --rtsp rtsp://192.168.1.10:554/stream
call .venv\Scripts\python.exe -m raptor_hud.main %*
