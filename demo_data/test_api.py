"""
Скрипт тестирования API цифрового двойника.

Запуск:
    1. Убедись, что сервер запущен: python manage.py runserver
    2. В другом терминале: python demo_data/test_api.py

Скрипт последовательно:
    1. Создаёт товары
    2. Создаёт локации
    3. Создаёт заказ
    4. Отправляет события полного цикла партии
    5. Проверяет защиту от дубликатов
"""

import json
import sys
import urllib.request
import urllib.error

BASE_URL = 'http://127.0.0.1:8000/api/v1'


def post(endpoint, data):
    """Отправляет POST-запрос и возвращает результат."""
    url = f'{BASE_URL}/{endpoint}'
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            status_code = resp.status
    except urllib.error.HTTPError as e:
        result = json.loads(e.read().decode('utf-8'))
        status_code = e.code

    return status_code, result


def get(endpoint):
    """Отправляет GET-запрос."""
    url = f'{BASE_URL}/{endpoint}'
    req = urllib.request.Request(url, method='GET')
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))


def section(title):
    print(f'\n{"="*60}')
    print(f'  {title}')
    print(f'{"="*60}')


def step(description, status_code, result):
    icon = '✅' if status_code in (200, 201) else '❌'
    print(f'{icon} [{status_code}] {description}')
    if status_code not in (200, 201):
        print(f'   Ответ: {json.dumps(result, ensure_ascii=False, indent=2)}')


def main():
    print('🚀 Тестирование API цифрового двойника складской логистики')
    print(f'   Сервер: {BASE_URL}')

    # ----- 1. Справочники -----
    section('1. Создание справочников')

    products = [
        {'sku_code': 'SKU-1001', 'product_name': 'Ноутбук Dell XPS 15', 'unit_of_measure': 'шт'},
        {'sku_code': 'SKU-1002', 'product_name': 'Монитор LG 27"', 'unit_of_measure': 'шт'},
        {'sku_code': 'SKU-1003', 'product_name': 'Клавиатура Logitech MX', 'unit_of_measure': 'шт'},
    ]
    for p in products:
        code, result = post('reference/products/', p)
        step(f'Товар {p["sku_code"]}', code, result)

    locations = [
        {'location_code': 'RECEIVING-01', 'location_name': 'Зона приёмки 1', 'location_type': 'receiving'},
        {'location_code': 'A-01-01', 'location_name': 'Стеллаж A, полка 1, ячейка 1', 'location_type': 'storage'},
        {'location_code': 'A-01-02', 'location_name': 'Стеллаж A, полка 1, ячейка 2', 'location_type': 'storage'},
        {'location_code': 'A-01-03', 'location_name': 'Стеллаж A, полка 1, ячейка 3', 'location_type': 'storage'},
        {'location_code': 'PICKING-01', 'location_name': 'Зона комплектации 1', 'location_type': 'picking'},
        {'location_code': 'SHIPPING-01', 'location_name': 'Зона отгрузки 1', 'location_type': 'shipping'},
    ]
    for loc in locations:
        code, result = post('reference/locations/', loc)
        step(f'Локация {loc["location_code"]}', code, result)

    # ----- 2. Событие: партия принята -----
    section('2. Приём партии на склад')

    code, result = post('events/', {
        'event_id': 'evt-001',
        'event_type': 'batch.received',
        'occurred_at': '2026-03-20T08:00:00Z',
        'source_system': 'simulator',
        'warehouse_code': 'WH-01',
        'object_type': 'batch',
        'object_id': 'BATCH-00045',
        'payload': {
            'batch_code': 'BATCH-00045',
            'product_sku': 'SKU-1001',
            'qty': 120,
            'supplier_doc': 'SUP-2026-100',
            'receiving_gate': 'RECEIVING-01',
        }
    })
    step('batch.received — BATCH-00045', code, result)

    # ----- 3. Событие: партия размещена -----
    section('3. Размещение партии в ячейке')

    code, result = post('events/', {
        'event_id': 'evt-002',
        'event_type': 'batch.placed',
        'occurred_at': '2026-03-20T08:30:00Z',
        'source_system': 'simulator',
        'warehouse_code': 'WH-01',
        'object_type': 'batch',
        'object_id': 'BATCH-00045',
        'payload': {
            'batch_code': 'BATCH-00045',
            'qty': 120,
            'to_location': 'A-01-03',
            'zone_code': 'STORAGE-A',
        }
    })
    step('batch.placed — BATCH-00045 → A-01-03', code, result)

    # ----- 4. Создание заказа через событие -----
    section('4. Создание заказа')

    code, result = post('events/', {
        'event_id': 'evt-003',
        'event_type': 'order.created',
        'occurred_at': '2026-03-20T09:00:00Z',
        'source_system': 'simulator',
        'warehouse_code': 'WH-01',
        'object_type': 'order',
        'object_id': 'ORD-2026-0001',
        'payload': {
            'order_number': 'ORD-2026-0001',
            'priority': 'high',
            'planned_ship_at': '2026-03-21T18:00:00Z',
            'items': [
                {'product_sku': 'SKU-1001', 'qty_requested': 10},
                {'product_sku': 'SKU-1002', 'qty_requested': 5},
            ]
        }
    })
    step('order.created — ORD-2026-0001', code, result)

    # ----- 5. Резервирование партии -----
    section('5. Резервирование партии под заказ')

    code, result = post('events/', {
        'event_id': 'evt-004',
        'event_type': 'batch.reserved',
        'occurred_at': '2026-03-20T09:15:00Z',
        'source_system': 'simulator',
        'warehouse_code': 'WH-01',
        'object_type': 'batch',
        'object_id': 'BATCH-00045',
        'payload': {
            'batch_code': 'BATCH-00045',
            'order_number': 'ORD-2026-0001',
            'qty_reserved': 10,
        }
    })
    step('batch.reserved — 10 шт из BATCH-00045 → ORD-2026-0001', code, result)

    # ----- 6. Комплектация -----
    section('6. Комплектация заказа')

    code, result = post('events/', {
        'event_id': 'evt-005',
        'event_type': 'order.picking_started',
        'occurred_at': '2026-03-20T10:00:00Z',
        'source_system': 'simulator',
        'warehouse_code': 'WH-01',
        'object_type': 'order',
        'object_id': 'ORD-2026-0001',
        'payload': {
            'order_number': 'ORD-2026-0001',
        }
    })
    step('order.picking_started — ORD-2026-0001', code, result)

    code, result = post('events/', {
        'event_id': 'evt-006',
        'event_type': 'order.item_picked',
        'occurred_at': '2026-03-20T10:15:00Z',
        'source_system': 'simulator',
        'warehouse_code': 'WH-01',
        'object_type': 'order',
        'object_id': 'ORD-2026-0001',
        'payload': {
            'order_number': 'ORD-2026-0001',
            'product_sku': 'SKU-1001',
            'qty_picked': 10,
            'batch_code': 'BATCH-00045',
        }
    })
    step('order.item_picked — SKU-1001 × 10', code, result)

    code, result = post('events/', {
        'event_id': 'evt-007',
        'event_type': 'order.assembled',
        'occurred_at': '2026-03-20T10:30:00Z',
        'source_system': 'simulator',
        'warehouse_code': 'WH-01',
        'object_type': 'order',
        'object_id': 'ORD-2026-0001',
        'payload': {
            'order_number': 'ORD-2026-0001',
            'assembled_at': '2026-03-20T10:30:00Z',
        }
    })
    step('order.assembled — ORD-2026-0001', code, result)

    # ----- 7. Отгрузка -----
    section('7. Отгрузка')

    code, result = post('events/', {
        'event_id': 'evt-008',
        'event_type': 'shipment.dispatched',
        'occurred_at': '2026-03-20T14:00:00Z',
        'source_system': 'simulator',
        'warehouse_code': 'WH-01',
        'object_type': 'order',
        'object_id': 'ORD-2026-0001',
        'payload': {
            'order_number': 'ORD-2026-0001',
            'shipment_number': 'SHP-2026-0001',
            'dispatched_at': '2026-03-20T14:00:00Z',
        }
    })
    step('shipment.dispatched — ORD-2026-0001', code, result)

    # ----- 8. Проверка дубликата -----
    section('8. Проверка защиты от дубликатов')

    code, result = post('events/', {
        'event_id': 'evt-001',  # Тот же event_id, что и в шаге 2
        'event_type': 'batch.received',
        'occurred_at': '2026-03-20T08:00:00Z',
        'source_system': 'simulator',
        'warehouse_code': 'WH-01',
        'object_type': 'batch',
        'object_id': 'BATCH-00045',
        'payload': {
            'batch_code': 'BATCH-00045',
            'product_sku': 'SKU-1001',
            'qty': 120,
        }
    })
    expected_dup = result.get('status') == 'duplicate'
    icon = '✅' if expected_dup else '❌'
    print(f'{icon} [{code}] Дубликат evt-001 → status={result.get("status")}')

    # ----- 9. Итоговая проверка данных -----
    section('9. Проверка состояния объектов')

    batches = get('batches/')
    if batches:
        b = batches[0]
        print(f'📦 Партия: {b["batch_number"]}')
        print(f'   Статус: {b["current_stage"]}')
        print(f'   Локация: {b["current_location"]}')
        print(f'   Всего: {b["quantity_total"]}, Доступно: {b["quantity_available"]}')

    orders = get('orders/')
    if orders:
        o = orders[0]
        print(f'📋 Заказ: {o["order_number"]}')
        print(f'   Статус: {o["current_stage"]}')
        print(f'   Выполнение: {o["completion_percent"]}%')

    print(f'\n{"="*60}')
    print('  ✅ Тестирование завершено!')
    print(f'{"="*60}\n')


if __name__ == '__main__':
    try:
        main()
    except urllib.error.URLError:
        print('❌ Не удалось подключиться к серверу.')
        print('   Убедись, что сервер запущен: python manage.py runserver')
        sys.exit(1)
