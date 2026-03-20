"""URL-маршруты веб-интерфейса."""

from django.urls import path
from . import views

app_name = 'ui'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Digital Twin
    path('digital-twin/', views.digital_twin, name='digital-twin'),

    # Batches
    path('batches/', views.batch_list, name='batch-list'),
    path('batches/<int:batch_id>/', views.batch_detail, name='batch-detail'),

    # Orders
    path('orders/', views.order_list, name='order-list'),
    path('orders/<int:order_id>/', views.order_detail, name='order-detail'),

    # Events
    path('events/', views.event_list, name='event-list'),
    path('events/<int:event_id>/', views.event_detail, name='event-detail'),

    # Locations
    path('locations/', views.location_list, name='location-list'),

    # Analytics
    path('analytics/', views.analytics, name='analytics'),

    # Simulator
    path('simulator/', views.simulator, name='simulator'),
]
