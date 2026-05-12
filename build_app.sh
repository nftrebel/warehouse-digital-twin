#!/usr/bin/env bash
# Сборка macOS .app для «Цифрового двойника склада».
# Запуск:  bash build_app.sh

set -e

echo "=== Установка зависимостей ==="
pip install -r requirements.txt

echo "=== Очистка предыдущих сборок ==="
rm -rf build dist

echo "=== Сборка через PyInstaller ==="
pyinstaller desktop.spec --noconfirm

echo
echo "=== Готово! ==="
echo "Приложение:  dist/WarehouseDigitalTwin.app"
echo "Папка-сборка: dist/WarehouseDigitalTwin/"
