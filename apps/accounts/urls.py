"""URL-маршруты аутентификации и управления пользователями."""

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Аутентификация
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Управление пользователями (UC-11, только для администраторов)
    path('users/', views.user_list, name='user-list'),
    path('users/create/', views.user_create, name='user-create'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user-edit'),
    path('users/<int:user_id>/toggle/', views.user_toggle_active, name='user-toggle'),
]
