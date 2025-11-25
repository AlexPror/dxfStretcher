@echo off
setlocal

REM Переходим в папку проекта
cd /d "%~dp0"

REM Проверяем наличие виртуального окружения
if not exist ".venv\Scripts\python.exe" (
    echo [*] Создаю виртуальное окружение...
    python -m venv .venv
    if errorlevel 1 (
        echo [!] Не удалось создать виртуальное окружение.
        exit /b 1
    )
)

echo [*] Обновляю зависимости...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
call ".venv\Scripts\pip.exe" install -r requirements.txt

echo [*] Запускаю приложение FlatPatternStretcher...
call ".venv\Scripts\python.exe" app.py

endlocal

