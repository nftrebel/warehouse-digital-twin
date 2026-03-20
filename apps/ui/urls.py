"""
URL-маршруты веб-интерфейса.

Экраны:
    /                  — Главный дашборд
    /digital-twin/     — Экран цифрового двойника
    /events/           — Журнал событий
    /batches/          — Партии товара
    /orders/           — Заказы
    /locations/        — Склад и ячейки
    /analytics/        — Аналитика и KPI
    /references/       — Справочники
"""

from django.urls import path

app_name = 'ui'

urlpatterns = [
    # Экраны будут добавлены на этапе 4
]
