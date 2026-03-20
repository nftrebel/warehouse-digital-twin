"""
URL-маршруты REST API.

Эндпоинты:
    POST /api/v1/events/              — приём одного события
    POST /api/v1/events/bulk/         — пакетная загрузка событий
    GET/POST /api/v1/reference/products/  — товары
    GET/POST /api/v1/reference/locations/ — локации
    GET/POST /api/v1/batches/         — партии
    GET/POST /api/v1/orders/          — заказы
"""

from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    # Основной приём событий
    path('events/', views.event_receive, name='event-receive'),
    path('events/bulk/', views.event_bulk_receive, name='event-bulk-receive'),

    # Справочники
    path('reference/products/', views.product_list_create, name='product-list-create'),
    path('reference/locations/', views.location_list_create, name='location-list-create'),

    # Партии и заказы
    path('batches/', views.batch_list_create, name='batch-list-create'),
    path('orders/', views.order_list_create, name='order-list-create'),
]
