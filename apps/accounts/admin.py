from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'full_name', 'role_code', 'is_active', 'date_joined')
    list_filter = ('role_code', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Роль в системе', {'fields': ('role_code', 'full_name')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Роль в системе', {'fields': ('role_code', 'full_name')}),
    )
