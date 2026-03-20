"""
Модель пользователя: User.

Кастомная модель пользователя на основе AbstractUser.
Роли (аналитик / администратор) хранятся полем role_code
без отдельной таблицы Role — упрощение для MVP.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Учётная запись пользователя системы.

    Расширяет стандартного Django-пользователя полями role_code и is_active.
    Поддерживает две роли: аналитик и администратор.

    Поля из AbstractUser (уже есть):
        username, password, first_name, last_name, email, is_active,
        is_staff, is_superuser, date_joined
    """

    ROLE_CHOICES = [
        ('analyst', 'Аналитик'),
        ('admin', 'Администратор'),
    ]

    role_code = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='analyst',
        verbose_name='Роль',
    )
    full_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Полное имя',
    )

    class Meta:
        db_table = 'user'
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return f'{self.username} ({self.get_role_code_display()})'

    @property
    def is_analyst(self):
        return self.role_code == 'analyst'

    @property
    def is_admin_role(self):
        return self.role_code == 'admin'
