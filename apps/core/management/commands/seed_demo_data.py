"""
Полная загрузка демонстрационных данных цифрового двойника.

Покрытие:
  UC-1..UC-9, UC-11, FR-1..FR-25, FR-29..FR-31
  Все 11 типов событий, партии/заказы на всех этапах,
  просроченные заказы, блокировка локаций, данные для KPI.

Запуск:
    python manage.py seed_demo_data
    python manage.py seed_demo_data --clear   (с очисткой)
"""
import uuid
from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count

from apps.references.models import Product, StorageLocation
from apps.inventory.models import Batch, BatchReservation
from apps.orders.models import CustomerOrder, OrderLine
from apps.events.models import ProcessEvent
from apps.events.services import EventProcessor


class Command(BaseCommand):
    help = 'Загружает полный набор демо-данных цифрового двойника'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true',
                            help='Очистить данные перед загрузкой')

    def handle(self, *args, **options):
        if options['clear']:
            self._clear()
        self.now = timezone.now()
        self.ep = EventProcessor()
        self.cnt = 0

        self.stdout.write(self.style.MIGRATE_HEADING(
            '\n🏭 Загрузка демонстрационных данных\n'))
        self._products()
        self._locations()
        self._scenario1_full_cycles()
        self._scenario2_multi_orders()
        self._scenario3_partial_states()
        self._scenario4_delays()
        self._scenario5_location_ops()
        self._scenario6_analytics_bulk()
        self._summary()

    # ---- helpers ----
    def _evt(self, etype, occ, payload, otype, oid, src='simulator'):
        self.cnt += 1
        r = self.ep.process_event({
            'event_id': f'demo-{uuid.uuid4().hex[:12]}',
            'event_type': etype, 'occurred_at': occ,
            'source_system': src, 'warehouse_code': 'WH-01',
            'object_type': otype, 'object_id': oid, 'payload': payload,
        })
        if r['status'] not in ('accepted', 'duplicate'):
            self.stdout.write(self.style.WARNING(
                f'   ⚠ {etype} {oid}: {r["message"]}'))

    def _clear(self):
        self.stdout.write('🗑  Очистка...')
        for m in [ProcessEvent, BatchReservation, OrderLine,
                  CustomerOrder, Batch, StorageLocation, Product]:
            m.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('   ✅ Очищено'))

    # ---- справочники ----
    def _products(self):
        self.stdout.write('📦 Товары...')
        data = [
            ('SKU-1001', 'Ноутбук Dell XPS 15', 'шт'),
            ('SKU-1002', 'Монитор LG UltraWide 34"', 'шт'),
            ('SKU-1003', 'Клавиатура Logitech MX Keys', 'шт'),
            ('SKU-1004', 'Мышь Razer DeathAdder', 'шт'),
            ('SKU-1005', 'SSD Samsung 970 EVO 1TB', 'шт'),
            ('SKU-1006', 'Кабель HDMI 2.1 (2м)', 'шт'),
            ('SKU-1007', 'USB-хаб Anker 7-в-1', 'шт'),
            ('SKU-1008', 'Веб-камера Logitech C920', 'шт'),
            ('SKU-1009', 'Наушники Sony WH-1000XM5', 'шт'),
            ('SKU-1010', 'Зарядное устройство Apple 96W', 'шт'),
            ('SKU-2001', 'Бумага А4 (500 л.)', 'уп'),
            ('SKU-2002', 'Картридж HP LaserJet', 'шт'),
        ]
        for s, n, u in data:
            Product.objects.get_or_create(sku_code=s,
                                         defaults={'product_name': n, 'unit_of_measure': u})
        self.stdout.write(self.style.SUCCESS(f'   ✅ {len(data)} товаров'))

    def _locations(self):
        self.stdout.write('📍 Локации...')
        data = [
            ('RECV-01', 'Зона приёмки — Ворота 1', 'receiving'),
            ('RECV-02', 'Зона приёмки — Ворота 2', 'receiving'),
            ('A-01-01', 'Стеллаж A, ярус 1, ячейка 1', 'storage'),
            ('A-01-02', 'Стеллаж A, ярус 1, ячейка 2', 'storage'),
            ('A-01-03', 'Стеллаж A, ярус 1, ячейка 3', 'storage'),
            ('A-02-01', 'Стеллаж A, ярус 2, ячейка 1', 'storage'),
            ('A-02-02', 'Стеллаж A, ярус 2, ячейка 2', 'storage'),
            ('B-01-01', 'Стеллаж B, ярус 1, ячейка 1', 'storage'),
            ('B-01-02', 'Стеллаж B, ярус 1, ячейка 2', 'storage'),
            ('B-02-01', 'Стеллаж B, ярус 2, ячейка 1', 'storage'),
            ('PICK-01', 'Зона комплектации 1', 'picking'),
            ('PICK-02', 'Зона комплектации 2', 'picking'),
            ('BUF-01', 'Буферная зона 1', 'buffer'),
            ('SHIP-01', 'Зона отгрузки — Док 1', 'shipping'),
            ('SHIP-02', 'Зона отгрузки — Док 2', 'shipping'),
        ]
        for c, n, t in data:
            StorageLocation.objects.get_or_create(
                location_code=c,
                defaults={'location_name': n, 'location_type': t})
        self.stdout.write(self.style.SUCCESS(f'   ✅ {len(data)} локаций'))

    # ==== Сценарий 1: Полные циклы (UC-1,2,5,6  FR-1..6,12..14) ====
    def _scenario1_full_cycles(self):
        self.stdout.write('\n🔄 Сценарий 1: Полные жизненные циклы')
        b = self.now - timedelta(days=3)

        # Партия 1 + Заказ 1: полный путь до отгрузки
        self._evt('batch.received', b, {
            'batch_code': 'BATCH-001', 'product_sku': 'SKU-1001',
            'qty': 50, 'supplier_doc': 'SUP-001', 'receiving_gate': 'RECV-01',
        }, 'batch', 'BATCH-001', 'scanner')
        self._evt('batch.placed', b+timedelta(hours=1), {
            'batch_code': 'BATCH-001', 'qty': 50,
            'to_location': 'A-01-01', 'zone_code': 'STORAGE-A',
        }, 'batch', 'BATCH-001', 'scanner')
        self._evt('order.created', b+timedelta(hours=2), {
            'order_number': 'ORD-001', 'priority': 'high',
            'planned_ship_at': (b+timedelta(days=1, hours=18)).isoformat(),
            'items': [{'product_sku': 'SKU-1001', 'qty_requested': 15}],
        }, 'order', 'ORD-001')
        self._evt('batch.reserved', b+timedelta(hours=3), {
            'batch_code': 'BATCH-001', 'order_number': 'ORD-001', 'qty_reserved': 15,
        }, 'batch', 'BATCH-001')
        self._evt('order.picking_started', b+timedelta(hours=4), {
            'order_number': 'ORD-001',
        }, 'order', 'ORD-001')
        self._evt('order.item_picked', b+timedelta(hours=4, minutes=30), {
            'order_number': 'ORD-001', 'product_sku': 'SKU-1001',
            'qty_picked': 15, 'batch_code': 'BATCH-001',
        }, 'order', 'ORD-001', 'scanner')
        self._evt('order.assembled', b+timedelta(hours=5), {
            'order_number': 'ORD-001',
            'assembled_at': (b+timedelta(hours=5)).isoformat(),
        }, 'order', 'ORD-001')
        self._evt('shipment.dispatched', b+timedelta(hours=8), {
            'order_number': 'ORD-001', 'shipment_number': 'SHP-001',
            'dispatched_at': (b+timedelta(hours=8)).isoformat(),
        }, 'order', 'ORD-001')
        self.stdout.write('   ✅ BATCH-001 + ORD-001: полный цикл → shipped')

        # Партия 2 + Заказ 2: с перемещением (batch.moved)
        self._evt('batch.received', b+timedelta(hours=1), {
            'batch_code': 'BATCH-002', 'product_sku': 'SKU-1002',
            'qty': 30, 'supplier_doc': 'SUP-002', 'receiving_gate': 'RECV-02',
        }, 'batch', 'BATCH-002', 'scanner')
        self._evt('batch.placed', b+timedelta(hours=2), {
            'batch_code': 'BATCH-002', 'qty': 30,
            'to_location': 'A-01-02', 'zone_code': 'STORAGE-A',
        }, 'batch', 'BATCH-002', 'scanner')
        self._evt('batch.moved', b+timedelta(hours=6), {
            'batch_code': 'BATCH-002', 'qty': 30,
            'from_location': 'A-01-02', 'to_location': 'B-01-01',
        }, 'batch', 'BATCH-002', 'scanner')
        self._evt('order.created', b+timedelta(hours=7), {
            'order_number': 'ORD-002', 'priority': 'normal',
            'planned_ship_at': (b+timedelta(days=2)).isoformat(),
            'items': [{'product_sku': 'SKU-1002', 'qty_requested': 10}],
        }, 'order', 'ORD-002')
        self._evt('batch.reserved', b+timedelta(hours=8), {
            'batch_code': 'BATCH-002', 'order_number': 'ORD-002', 'qty_reserved': 10,
        }, 'batch', 'BATCH-002')
        self._evt('order.picking_started', b+timedelta(hours=9), {
            'order_number': 'ORD-002',
        }, 'order', 'ORD-002')
        self._evt('order.item_picked', b+timedelta(hours=9, minutes=20), {
            'order_number': 'ORD-002', 'product_sku': 'SKU-1002',
            'qty_picked': 10, 'batch_code': 'BATCH-002',
        }, 'order', 'ORD-002', 'scanner')
        self._evt('order.assembled', b+timedelta(hours=10), {
            'order_number': 'ORD-002',
            'assembled_at': (b+timedelta(hours=10)).isoformat(),
        }, 'order', 'ORD-002')
        self._evt('shipment.dispatched', b+timedelta(hours=12), {
            'order_number': 'ORD-002', 'shipment_number': 'SHP-002',
            'dispatched_at': (b+timedelta(hours=12)).isoformat(),
        }, 'order', 'ORD-002')
        self.stdout.write('   ✅ BATCH-002 + ORD-002: с batch.moved → shipped')

    # ==== Сценарий 2: Многопозиционные заказы (UC-5 FR-12..14) ====
    def _scenario2_multi_orders(self):
        self.stdout.write('\n📋 Сценарий 2: Многопозиционные заказы')
        b = self.now - timedelta(days=2)

        for i, (sku, qty, loc) in enumerate([
            ('SKU-1003', 200, 'A-01-03'), ('SKU-1004', 150, 'A-02-01'),
            ('SKU-1005', 100, 'A-02-02'), ('SKU-1006', 500, 'B-01-02'),
            ('SKU-1007', 80, 'B-02-01'),
        ], start=3):
            c = f'BATCH-{i:03d}'
            self._evt('batch.received', b+timedelta(hours=i), {
                'batch_code': c, 'product_sku': sku, 'qty': qty,
                'supplier_doc': f'SUP-{i:03d}', 'receiving_gate': 'RECV-01',
            }, 'batch', c, 'import')
            self._evt('batch.placed', b+timedelta(hours=i, minutes=40), {
                'batch_code': c, 'qty': qty, 'to_location': loc,
            }, 'batch', c, 'scanner')

        # ORD-003: urgent, 3 позиции, частичная комплектация
        self._evt('order.created', b+timedelta(hours=10), {
            'order_number': 'ORD-003', 'priority': 'urgent',
            'planned_ship_at': (self.now+timedelta(hours=6)).isoformat(),
            'items': [
                {'product_sku': 'SKU-1003', 'qty_requested': 20},
                {'product_sku': 'SKU-1004', 'qty_requested': 10},
                {'product_sku': 'SKU-1005', 'qty_requested': 5},
            ],
        }, 'order', 'ORD-003')
        for bc, on, qr in [('BATCH-003','ORD-003',20),
                           ('BATCH-004','ORD-003',10),
                           ('BATCH-005','ORD-003',5)]:
            self._evt('batch.reserved', b+timedelta(hours=11), {
                'batch_code': bc, 'order_number': on, 'qty_reserved': qr,
            }, 'batch', bc)
        self._evt('order.picking_started', b+timedelta(hours=12), {
            'order_number': 'ORD-003',
        }, 'order', 'ORD-003')
        self._evt('order.item_picked', b+timedelta(hours=12, minutes=15), {
            'order_number': 'ORD-003', 'product_sku': 'SKU-1003',
            'qty_picked': 20, 'batch_code': 'BATCH-003',
        }, 'order', 'ORD-003', 'scanner')
        self.stdout.write('   ✅ ORD-003: urgent, 3 позиции, picking (1/3)')

        # ORD-004: создан, ожидает
        self._evt('order.created', b+timedelta(hours=14), {
            'order_number': 'ORD-004', 'priority': 'normal',
            'planned_ship_at': (self.now+timedelta(days=2)).isoformat(),
            'items': [
                {'product_sku': 'SKU-1006', 'qty_requested': 100},
                {'product_sku': 'SKU-1007', 'qty_requested': 15},
            ],
        }, 'order', 'ORD-004')
        self.stdout.write('   ✅ ORD-004: created, ожидает резервирования')

    # ==== Сценарий 3: Объекты на разных этапах (UC-6 FR-15..17) ====
    def _scenario3_partial_states(self):
        self.stdout.write('\n🔀 Сценарий 3: Объекты на разных этапах')
        b = self.now - timedelta(days=1)

        # BATCH-008: received (не размещена)
        self._evt('batch.received', b+timedelta(hours=1), {
            'batch_code': 'BATCH-008', 'product_sku': 'SKU-1008',
            'qty': 60, 'supplier_doc': 'SUP-008', 'receiving_gate': 'RECV-01',
        }, 'batch', 'BATCH-008', 'scanner')
        self.stdout.write('   ✅ BATCH-008: received')

        # BATCH-009: stored
        self._evt('batch.received', b+timedelta(hours=2), {
            'batch_code': 'BATCH-009', 'product_sku': 'SKU-1009',
            'qty': 40, 'supplier_doc': 'SUP-009', 'receiving_gate': 'RECV-02',
        }, 'batch', 'BATCH-009', 'import')
        self._evt('batch.placed', b+timedelta(hours=3), {
            'batch_code': 'BATCH-009', 'qty': 40, 'to_location': 'A-01-01',
        }, 'batch', 'BATCH-009', 'scanner')
        self.stdout.write('   ✅ BATCH-009: stored')

        # BATCH-010 + ORD-005: reserved
        self._evt('batch.received', b+timedelta(hours=2), {
            'batch_code': 'BATCH-010', 'product_sku': 'SKU-1010',
            'qty': 25, 'supplier_doc': 'SUP-010', 'receiving_gate': 'RECV-01',
        }, 'batch', 'BATCH-010', 'scanner')
        self._evt('batch.placed', b+timedelta(hours=3), {
            'batch_code': 'BATCH-010', 'qty': 25, 'to_location': 'B-01-02',
        }, 'batch', 'BATCH-010', 'scanner')
        self._evt('order.created', b+timedelta(hours=4), {
            'order_number': 'ORD-005', 'priority': 'high',
            'planned_ship_at': (self.now+timedelta(days=1)).isoformat(),
            'items': [{'product_sku': 'SKU-1010', 'qty_requested': 10}],
        }, 'order', 'ORD-005')
        self._evt('batch.reserved', b+timedelta(hours=5), {
            'batch_code': 'BATCH-010', 'order_number': 'ORD-005', 'qty_reserved': 10,
        }, 'batch', 'BATCH-010')
        self.stdout.write('   ✅ BATCH-010 + ORD-005: reserved')

        # BATCH-011,012: expected (без событий)
        for num, sku in [('BATCH-011','SKU-2001'), ('BATCH-012','SKU-2002')]:
            p = Product.objects.get(sku_code=sku)
            Batch.objects.get_or_create(batch_number=num, defaults={
                'product': p, 'quantity_total': Decimal('100'),
                'current_stage_code': 'expected'})
        self.stdout.write('   ✅ BATCH-011,012: expected')

        # ORD-006: assembled (ожидает отгрузки)
        self._evt('batch.received', b, {
            'batch_code': 'BATCH-013', 'product_sku': 'SKU-1006',
            'qty': 300, 'supplier_doc': 'SUP-013', 'receiving_gate': 'RECV-01',
        }, 'batch', 'BATCH-013', 'import')
        self._evt('batch.placed', b+timedelta(minutes=30), {
            'batch_code': 'BATCH-013', 'qty': 300, 'to_location': 'A-02-02',
        }, 'batch', 'BATCH-013', 'scanner')
        self._evt('order.created', b+timedelta(hours=1), {
            'order_number': 'ORD-006', 'priority': 'normal',
            'planned_ship_at': (self.now+timedelta(hours=12)).isoformat(),
            'items': [{'product_sku': 'SKU-1006', 'qty_requested': 50}],
        }, 'order', 'ORD-006')
        self._evt('batch.reserved', b+timedelta(hours=2), {
            'batch_code': 'BATCH-013', 'order_number': 'ORD-006', 'qty_reserved': 50,
        }, 'batch', 'BATCH-013')
        self._evt('order.picking_started', b+timedelta(hours=3), {
            'order_number': 'ORD-006',
        }, 'order', 'ORD-006')
        self._evt('order.item_picked', b+timedelta(hours=3, minutes=20), {
            'order_number': 'ORD-006', 'product_sku': 'SKU-1006',
            'qty_picked': 50, 'batch_code': 'BATCH-013',
        }, 'order', 'ORD-006', 'scanner')
        self._evt('order.assembled', b+timedelta(hours=4), {
            'order_number': 'ORD-006',
            'assembled_at': (b+timedelta(hours=4)).isoformat(),
        }, 'order', 'ORD-006')
        self.stdout.write('   ✅ ORD-006: assembled, ожидает отгрузки')

    # ==== Сценарий 4: Задержки (UC-7 FR-18..20) ====
    def _scenario4_delays(self):
        self.stdout.write('\n⚠️  Сценарий 4: Задержки и отклонения')
        b = self.now - timedelta(days=5)

        # ORD-007: ПРОСРОЧЕН, завис на picking
        self._evt('batch.received', b, {
            'batch_code': 'BATCH-014', 'product_sku': 'SKU-1003',
            'qty': 80, 'supplier_doc': 'SUP-014', 'receiving_gate': 'RECV-02',
        }, 'batch', 'BATCH-014', 'scanner')
        self._evt('batch.placed', b+timedelta(hours=2), {
            'batch_code': 'BATCH-014', 'qty': 80, 'to_location': 'A-01-03',
        }, 'batch', 'BATCH-014', 'scanner')
        self._evt('order.created', b+timedelta(hours=3), {
            'order_number': 'ORD-007', 'priority': 'urgent',
            'planned_ship_at': (self.now-timedelta(days=2)).isoformat(),
            'items': [{'product_sku': 'SKU-1003', 'qty_requested': 30}],
        }, 'order', 'ORD-007')
        self._evt('batch.reserved', b+timedelta(hours=4), {
            'batch_code': 'BATCH-014', 'order_number': 'ORD-007', 'qty_reserved': 30,
        }, 'batch', 'BATCH-014')
        self._evt('order.picking_started', b+timedelta(days=1), {
            'order_number': 'ORD-007',
        }, 'order', 'ORD-007')
        self.stdout.write('   ✅ ORD-007: ПРОСРОЧЕН, завис на picking')

        # ORD-008: просрочен, даже не резервирован
        self._evt('order.created', self.now-timedelta(days=4), {
            'order_number': 'ORD-008', 'priority': 'high',
            'planned_ship_at': (self.now-timedelta(days=1)).isoformat(),
            'items': [{'product_sku': 'SKU-1004', 'qty_requested': 5}],
        }, 'order', 'ORD-008')
        self.stdout.write('   ✅ ORD-008: ПРОСРОЧЕН, created, не резервирован')

        # BATCH-015: зависла на приёмке >48ч
        self._evt('batch.received', self.now-timedelta(days=2), {
            'batch_code': 'BATCH-015', 'product_sku': 'SKU-1009',
            'qty': 20, 'supplier_doc': 'SUP-015', 'receiving_gate': 'RECV-01',
        }, 'batch', 'BATCH-015', 'scanner')
        self.stdout.write('   ✅ BATCH-015: received >48ч (аномалия)')

    # ==== Сценарий 5: Блокировка локаций (location.*) ====
    def _scenario5_location_ops(self):
        self.stdout.write('\n🔒 Сценарий 5: Блокировка/разблокировка')
        b = self.now - timedelta(hours=12)

        self._evt('location.blocked', b, {
            'location_code': 'A-02-01', 'reason': 'Инвентаризация',
        }, 'location', 'A-02-01', 'manual')
        self._evt('location.unblocked', b+timedelta(hours=4), {
            'location_code': 'A-02-01',
        }, 'location', 'A-02-01', 'manual')
        self._evt('location.blocked', self.now-timedelta(hours=2), {
            'location_code': 'BUF-01', 'reason': 'Повреждение стеллажа',
        }, 'location', 'BUF-01', 'manual')
        self.stdout.write('   ✅ A-02-01: blocked→unblocked; BUF-01: blocked')

    # ==== Сценарий 6: Массовые данные для аналитики (UC-3,4,8 FR-7..11,21..25) ====
    def _scenario6_analytics_bulk(self):
        self.stdout.write('\n📊 Сценарий 6: Данные для аналитики и KPI')

        for d in range(7, 3, -1):
            b = self.now - timedelta(days=d)
            idx = 20 + (7 - d)
            bc = f'BATCH-{idx:03d}'
            oc = f'ORD-{idx:03d}'
            sku = f'SKU-100{(idx % 7) + 1}'
            qty = 30 + idx * 5

            self._evt('batch.received', b, {
                'batch_code': bc, 'product_sku': sku, 'qty': qty,
                'supplier_doc': f'SUP-{idx:03d}',
                'receiving_gate': 'RECV-01' if idx % 2 == 0 else 'RECV-02',
            }, 'batch', bc, 'import')
            self._evt('batch.placed', b+timedelta(minutes=30+idx*3), {
                'batch_code': bc, 'qty': qty,
                'to_location': f'A-0{(idx%2)+1}-0{(idx%3)+1}',
            }, 'batch', bc, 'scanner')
            self._evt('order.created', b+timedelta(hours=2), {
                'order_number': oc,
                'priority': ['low','normal','high'][idx % 3],
                'planned_ship_at': (b+timedelta(days=1, hours=18)).isoformat(),
                'items': [{'product_sku': sku, 'qty_requested': 10+idx}],
            }, 'order', oc)
            self._evt('batch.reserved', b+timedelta(hours=3), {
                'batch_code': bc, 'order_number': oc, 'qty_reserved': 10+idx,
            }, 'batch', bc)
            self._evt('order.picking_started', b+timedelta(hours=4), {
                'order_number': oc,
            }, 'order', oc)
            self._evt('order.item_picked', b+timedelta(hours=4, minutes=20+idx*2), {
                'order_number': oc, 'product_sku': sku,
                'qty_picked': 10+idx, 'batch_code': bc,
            }, 'order', oc, 'scanner')
            self._evt('order.assembled', b+timedelta(hours=5+idx%3), {
                'order_number': oc,
                'assembled_at': (b+timedelta(hours=5+idx%3)).isoformat(),
            }, 'order', oc)
            self._evt('shipment.dispatched', b+timedelta(hours=7+idx%4), {
                'order_number': oc, 'shipment_number': f'SHP-{idx:03d}',
                'dispatched_at': (b+timedelta(hours=7+idx%4)).isoformat(),
            }, 'order', oc)

        self.stdout.write('   ✅ 4 полных цикла (разные скорости) для KPI')

    # ---- итоги ----
    def _summary(self):
        self.stdout.write(self.style.MIGRATE_HEADING('\n📊 Итоги:\n'))
        for label, model in [('Товаров', Product), ('Локаций', StorageLocation),
                             ('Партий', Batch), ('Заказов', CustomerOrder),
                             ('Строк заказов', OrderLine),
                             ('Резервирований', BatchReservation),
                             ('Событий', ProcessEvent)]:
            self.stdout.write(f'   {label:20s} {model.objects.count()}')

        self.stdout.write(self.style.MIGRATE_HEADING('\n📦 Партии по этапам:'))
        for r in Batch.objects.values('current_stage_code').annotate(
                c=Count('batch_id')).order_by('current_stage_code'):
            self.stdout.write(f'   {r["current_stage_code"]:15s} → {r["c"]}')

        self.stdout.write(self.style.MIGRATE_HEADING('\n📋 Заказы по этапам:'))
        for r in CustomerOrder.objects.values('current_stage_code').annotate(
                c=Count('order_id')).order_by('current_stage_code'):
            self.stdout.write(f'   {r["current_stage_code"]:15s} → {r["c"]}')

        overdue = CustomerOrder.objects.filter(
            planned_ship_date__lt=self.now
        ).exclude(current_stage_code__in=['shipped','closed','cancelled']).count()
        self.stdout.write(f'\n   ⚠️  Просроченных заказов: {overdue}')
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Всего событий: {self.cnt}'
            f'\n🚀 Откройте http://127.0.0.1:8000/\n'))
