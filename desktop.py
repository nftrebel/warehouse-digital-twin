"""
Десктопная обёртка для Django-приложения.

Запускает встроенный WSGI-сервер и открывает окно PyWebView,
указывающее на http://127.0.0.1:<PORT>. Используется как точка
входа для PyInstaller-сборки (.exe для Windows, .app для macOS).
"""

import os
import socket
import sys
import threading
import time
from pathlib import Path
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server


# ---------------------------------------------------------------------------
# Resource paths: учитываем PyInstaller frozen mode
# ---------------------------------------------------------------------------

def get_resource_dir() -> Path:
    """Каталог с ресурсами (templates/, static/, apps/, config/)."""
    if getattr(sys, "frozen", False):
        # PyInstaller --onedir: ресурсы рядом с исполняемым файлом
        # PyInstaller --onefile: распакованы в _MEIPASS
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def get_data_dir() -> Path:
    """Каталог для записи (БД, логи)."""
    if getattr(sys, "frozen", False):
        # Рядом с исполняемым файлом — пользователь видит db.sqlite3
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


RESOURCE_DIR = get_resource_dir()
DATA_DIR = get_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Чтобы Django нашёл config/, apps/ и т.д.
sys.path.insert(0, str(RESOURCE_DIR))
os.chdir(RESOURCE_DIR)

# Передаём путь к БД в settings.py
os.environ["WAREHOUSE_DATA_DIR"] = str(DATA_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


# ---------------------------------------------------------------------------
# Инициализация Django + первый запуск
# ---------------------------------------------------------------------------

def init_django():
    import django
    django.setup()

    from django.core.management import call_command
    from django.db import connection

    # Миграции
    call_command("migrate", verbosity=0, interactive=False)

    # Первый запуск: создаём демо-данные, если БД пустая
    from apps.accounts.models import User
    if not User.objects.exists():
        try:
            call_command("create_demo_users", verbosity=0)
        except Exception as e:
            print(f"[warn] create_demo_users: {e}")
        try:
            call_command("seed_demo_data", verbosity=0)
        except Exception as e:
            print(f"[warn] seed_demo_data: {e}")

    connection.close()


# ---------------------------------------------------------------------------
# WSGI-сервер
# ---------------------------------------------------------------------------

class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


def find_free_port(default: int = 8765) -> int:
    """Подбираем свободный порт, начиная с default."""
    for port in range(default, default + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return default


def build_wsgi_app():
    """WSGI-приложение Django + раздача /static/ через WhiteNoise-подобную обёртку."""
    from django.core.wsgi import get_wsgi_application
    from django.conf import settings

    django_app = get_wsgi_application()

    static_root = Path(settings.STATICFILES_DIRS[0])
    static_url = settings.STATIC_URL.rstrip("/") + "/"

    def serve_static(environ, start_response):
        path_info = environ.get("PATH_INFO", "")
        if path_info.startswith(static_url):
            rel = path_info[len(static_url):]
            file_path = (static_root / rel).resolve()
            try:
                file_path.relative_to(static_root.resolve())
            except ValueError:
                start_response("403 Forbidden", [("Content-Type", "text/plain")])
                return [b"Forbidden"]
            if file_path.is_file():
                ctype = guess_content_type(file_path.name)
                data = file_path.read_bytes()
                start_response("200 OK", [
                    ("Content-Type", ctype),
                    ("Content-Length", str(len(data))),
                ])
                return [data]
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not Found"]
        return django_app(environ, start_response)

    return serve_static


def guess_content_type(filename: str) -> str:
    import mimetypes
    mimetypes.add_type("application/vnd.ms-htmlhelp", ".chm")
    mimetypes.add_type("text/html", ".htm")
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or "application/octet-stream"


_server = None  # WSGIServer instance, заполняется в run_server()


def run_server(port: int):
    global _server
    app = build_wsgi_app()
    _server = make_server("127.0.0.1", port, app, handler_class=QuietHandler)
    _server.serve_forever()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Цифровой двойник — запуск десктоп-версии…")
    init_django()

    port = find_free_port(8765)
    url = f"http://127.0.0.1:{port}/"

    thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    thread.start()

    # Ждём, пока сервер реально начнёт принимать соединения
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    print(f"Сервер: {url}")

    try:
        import webview
    except ImportError:
        print("PyWebView не установлен. Откройте URL в браузере:", url)
        thread.join()
        return

    window = webview.create_window(
        "Цифровой двойник склада — складская логистика",
        url,
        width=1400,
        height=900,
        min_size=(1024, 700),
    )
    webview.start()

    # Корректная остановка после закрытия окна
    if _server is not None:
        _server.shutdown()


if __name__ == "__main__":
    main()
