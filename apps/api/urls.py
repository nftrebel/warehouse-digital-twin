"""
URL-маршруты REST API.

Основные эндпоинты:
    POST /api/v1/events/           — приём одного события
    POST /api/v1/events/bulk/      — пакетная загрузка событий
    POST /api/v1/reference/products/   — создание товара
    POST /api/v1/reference/locations/  — создание локации
    POST /api/v1/batches/          — создание партии
    POST /api/v1/orders/           — создание заказа
    POST /api/v1/simulator/run/    — запуск симуляции
"""

from django.urls import path

app_name = 'api'

urlpatterns = [
    # Эндпоинты будут добавлены на этапе 2
]
