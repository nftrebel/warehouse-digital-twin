"""
Команда для загрузки демонстрационных справочных данных.

Использование:
    python manage.py seed_demo_data
"""

from django.core.management.base import BaseCommand
from apps.references.models import Product, StorageLocation


class Command(BaseCommand):
    help = 'Загрузить демонстрационные справочные данные (товары, локации)'

    def handle(self, *args, **options):
        self.stdout.write('Загрузка демонстрационных данных...\n')

        # --- Товары ---
        products = [
            ('SKU-1001', 'Ноутбук Dell Latitude 5540', 'шт'),
            ('SKU-1002', 'Монитор Samsung 27"', 'шт'),
            ('SKU-1003', 'Клавиатура Logitech MX Keys', 'шт'),
            ('SKU-1004', 'Мышь Logitech MX Master 3', 'шт'),
            ('SKU-1005', 'Кабель HDMI 2.0 (2м)', 'шт'),
            ('SKU-2001', 'Бумага A4 (пачка 500 листов)', 'шт'),
            ('SKU-2002', 'Картридж HP 26A', 'шт'),
            ('SKU-3001', 'Кресло офисное ErgoPlus', 'шт'),
            ('SKU-3002', 'Стол письменный 160×80', 'шт'),
            ('SKU-3003', 'Тумба подкатная 3 ящика', 'шт'),
        ]

        created_products = 0
        for sku, name, unit in products:
            _, created = Product.objects.get_or_create(
                sku_code=sku,
                defaults={'product_name': name, 'unit_of_measure': unit},
            )
            if created:
                created_products += 1

        self.stdout.write(f'  Товары: {created_products} создано, '
                          f'{len(products) - created_products} уже существовало\n')

        # --- Локации ---
        locations = [
            # Зона приёмки
            ('RECEIVING-01', 'Ворота приёмки №1', 'receiving'),
            ('RECEIVING-02', 'Ворота приёмки №2', 'receiving'),
            # Зона хранения A
            ('A-01-01', 'Стеллаж A, ряд 1, ячейка 1', 'storage'),
            ('A-01-02', 'Стеллаж A, ряд 1, ячейка 2', 'storage'),
            ('A-01-03', 'Стеллаж A, ряд 1, ячейка 3', 'storage'),
            ('A-02-01', 'Стеллаж A, ряд 2, ячейка 1', 'storage'),
            ('A-02-02', 'Стеллаж A, ряд 2, ячейка 2', 'storage'),
            # Зона хранения B
            ('B-01-01', 'Стеллаж B, ряд 1, ячейка 1', 'storage'),
            ('B-01-02', 'Стеллаж B, ряд 1, ячейка 2', 'storage'),
            ('B-02-01', 'Стеллаж B, ряд 2, ячейка 1', 'storage'),
            # Зона комплектации
            ('PICKING-01', 'Стол комплектации №1', 'picking'),
            ('PICKING-02', 'Стол комплектации №2', 'picking'),
            # Буферная зона
            ('BUFFER-01', 'Буферная зона №1', 'buffer'),
            # Зона отгрузки
            ('SHIPPING-01', 'Ворота отгрузки №1', 'shipping'),
            ('SHIPPING-02', 'Ворота отгрузки №2', 'shipping'),
        ]

        created_locations = 0
        for code, name, loc_type in locations:
            _, created = StorageLocation.objects.get_or_create(
                location_code=code,
                defaults={'location_name': name, 'location_type': loc_type},
            )
            if created:
                created_locations += 1

        self.stdout.write(f'  Локации: {created_locations} создано, '
                          f'{len(locations) - created_locations} уже существовало\n')

        self.stdout.write(self.style.SUCCESS('\nДемо-данные загружены успешно!'))
