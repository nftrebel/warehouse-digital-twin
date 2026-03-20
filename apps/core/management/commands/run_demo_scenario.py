"""
Команда для запуска демонстрационного сценария.

Загружает события из JSON-файла и пропускает их через сервис цифрового двойника.

Использование:
    python manage.py run_demo_scenario
    python manage.py run_demo_scenario --file demo_data/full_cycle_scenario.json
"""

import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.digital_twin.services import (
    digital_twin_service,
    DuplicateEventError,
    EventProcessingError,
)


class Command(BaseCommand):
    help = 'Запустить демонстрационный сценарий из JSON-файла'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='demo_data/full_cycle_scenario.json',
            help='Путь к JSON-файлу сценария (по умолчанию: demo_data/full_cycle_scenario.json)',
        )

    def handle(self, *args, **options):
        file_path = Path(settings.BASE_DIR) / options['file']

        if not file_path.exists():
            self.stderr.write(self.style.ERROR(f'Файл не найден: {file_path}'))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            scenario = json.load(f)

        events = scenario.get('events', [])
        description = scenario.get('description', 'Без описания')

        self.stdout.write(f'\nСценарий: {description}')
        self.stdout.write(f'Событий в файле: {len(events)}\n')
        self.stdout.write('-' * 60)

        accepted = 0
        duplicates = 0
        errors = 0

        for i, event_data in enumerate(events, 1):
            event_id = event_data.get('event_id', '?')
            event_type = event_data.get('event_type', '?')

            try:
                result = digital_twin_service.process_event(event_data)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  [{i:02d}] ✓ {event_type:<25} → {result["message"]}'
                    )
                )
                accepted += 1

            except DuplicateEventError:
                self.stdout.write(
                    self.style.WARNING(
                        f'  [{i:02d}] ⊘ {event_type:<25} → Дубликат (event_id={event_id})'
                    )
                )
                duplicates += 1

            except EventProcessingError as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'  [{i:02d}] ✗ {event_type:<25} → Ошибка: {e}'
                    )
                )
                errors += 1

        self.stdout.write('-' * 60)
        self.stdout.write(
            f'\nИтого: {accepted} принято, {duplicates} дубликатов, {errors} ошибок'
        )
        self.stdout.write(self.style.SUCCESS('\nСценарий завершён!\n'))
