"""
Команда для создания демонстрационных пользователей.

Использование:
    python manage.py create_demo_users
"""

from django.core.management.base import BaseCommand
from apps.accounts.models import User


class Command(BaseCommand):
    help = 'Создаёт демонстрационных пользователей: admin и analyst'

    def handle(self, *args, **options):
        # Администратор
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                password='admin123',
                full_name='Администратор системы',
                role_code='admin',
            )
            self.stdout.write(self.style.SUCCESS(
                '✅ Создан администратор: admin / admin123'
            ))
        else:
            self.stdout.write('⏭  Пользователь admin уже существует')

        # Аналитик
        if not User.objects.filter(username='analyst').exists():
            user = User.objects.create_user(
                username='analyst',
                password='analyst123',
                full_name='Аналитик склада',
                role_code='analyst',
            )
            self.stdout.write(self.style.SUCCESS(
                '✅ Создан аналитик: analyst / analyst123'
            ))
        else:
            self.stdout.write('⏭  Пользователь analyst уже существует')

        self.stdout.write(self.style.SUCCESS('\nГотово! Теперь можно войти в систему.'))
