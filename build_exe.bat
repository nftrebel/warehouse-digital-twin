@echo off
REM Сборка Windows-исполнимого файла (.exe) для «Цифрового двойника склада».
REM Требования: установлены Python 3.10+, pip, и зависимости из requirements.txt.

setlocal

echo === Установка зависимостей ===
pip install -r requirements.txt || goto :error

echo === Очистка предыдущих сборок ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo === Сборка через PyInstaller ===
pyinstaller desktop.spec --noconfirm || goto :error

echo.
echo === Готово! ===
echo Исполнимый файл: dist\WarehouseDigitalTwin\WarehouseDigitalTwin.exe
echo Папку dist\WarehouseDigitalTwin можно переносить целиком — это standalone-сборка.
echo.
pause
exit /b 0

:error
echo.
echo *** Сборка завершилась с ошибкой ***
pause
exit /b 1
