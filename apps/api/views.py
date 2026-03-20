"""
REST API Views.

Эндпоинты:
    POST /api/v1/events/              — приём одного события
    POST /api/v1/events/bulk/         — пакетная загрузка
    POST /api/v1/reference/products/  — создание товара
    POST /api/v1/reference/locations/ — создание локации
    POST /api/v1/batches/             — создание партии
    POST /api/v1/orders/              — создание заказа
"""

from decimal import Decimal
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.references.models import Product, StorageLocation
from apps.inventory.models import Batch
from apps.orders.models import CustomerOrder, OrderLine
from apps.events.services import EventProcessor

from .serializers import (
    EventSerializer,
    BulkEventSerializer,
    ProductSerializer,
    StorageLocationSerializer,
    BatchCreateSerializer,
    OrderCreateSerializer,
)


# ---------------------------------------------------------------------------
# Основной эндпоинт — приём события
# ---------------------------------------------------------------------------

@api_view(['POST'])
def event_receive(request):
    """
    POST /api/v1/events/

    Принимает одно событие складского процесса.
    Проверяет структуру, защищает от дубликатов, сохраняет в журнал
    и обновляет состояние цифрового двойника.
    """
    serializer = EventSerializer(data=request.data)

    # Проверяем на дубликат (специальная обработка)
    if not serializer.is_valid():
        errors = serializer.errors
        # Если ошибка только в event_id и это дубликат
        if 'event_id' in errors:
            event_id_errors = errors['event_id']
            if any('__DUPLICATE__' in str(e) for e in event_id_errors):
                return Response(
                    {
                        'status': 'duplicate',
                        'event_id': request.data.get('event_id'),
                        'processing_result': 'already_registered',
                        'message': 'Событие с таким event_id уже зарегистрировано',
                    },
                    status=status.HTTP_200_OK,
                )

        return Response(
            {
                'status': 'rejected',
                'event_id': request.data.get('event_id'),
                'processing_result': 'validation_failed',
                'message': 'Ошибка валидации входных данных',
                'errors': errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Обрабатываем событие
    processor = EventProcessor()
    result = processor.process_event(serializer.validated_data)

    if result['status'] == 'accepted':
        http_status = status.HTTP_201_CREATED
    elif result['status'] == 'duplicate':
        http_status = status.HTTP_200_OK
    elif result['status'] == 'rejected':
        http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

    return Response(result, status=http_status)


# ---------------------------------------------------------------------------
# Пакетная загрузка событий
# ---------------------------------------------------------------------------

@api_view(['POST'])
def event_bulk_receive(request):
    """
    POST /api/v1/events/bulk/

    Принимает массив событий. Обрабатывает каждое по отдельности.
    Возвращает результат по каждому событию.
    """
    events_data = request.data.get('events', [])
    if not events_data:
        return Response(
            {'status': 'rejected', 'message': 'Поле events обязательно и не должно быть пустым'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    processor = EventProcessor()
    results = []

    for event_data in events_data:
        serializer = EventSerializer(data=event_data)

        if not serializer.is_valid():
            errors = serializer.errors
            event_id = event_data.get('event_id', 'unknown')

            # Проверка на дубликат
            if 'event_id' in errors and any('__DUPLICATE__' in str(e) for e in errors['event_id']):
                results.append({
                    'status': 'duplicate',
                    'event_id': event_id,
                    'processing_result': 'already_registered',
                    'message': 'Событие уже зарегистрировано',
                })
            else:
                results.append({
                    'status': 'rejected',
                    'event_id': event_id,
                    'processing_result': 'validation_failed',
                    'message': 'Ошибка валидации',
                    'errors': errors,
                })
            continue

        result = processor.process_event(serializer.validated_data)
        results.append(result)

    accepted = sum(1 for r in results if r['status'] == 'accepted')
    total = len(results)

    return Response(
        {
            'total': total,
            'accepted': accepted,
            'results': results,
        },
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
def product_list_create(request):
    """
    GET  /api/v1/reference/products/ — список товаров
    POST /api/v1/reference/products/ — создание товара
    """
    if request.method == 'GET':
        products = Product.objects.all()
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)

    serializer = ProductSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
def location_list_create(request):
    """
    GET  /api/v1/reference/locations/ — список локаций
    POST /api/v1/reference/locations/ — создание локации
    """
    if request.method == 'GET':
        locations = StorageLocation.objects.all()
        serializer = StorageLocationSerializer(locations, many=True)
        return Response(serializer.data)

    serializer = StorageLocationSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Создание партий и заказов (вспомогательное)
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
def batch_list_create(request):
    """
    GET  /api/v1/batches/ — список партий
    POST /api/v1/batches/ — создание стартовой партии
    """
    if request.method == 'GET':
        batches = Batch.objects.select_related('product', 'current_location').all()
        data = [
            {
                'batch_id': b.batch_id,
                'batch_number': b.batch_number,
                'product_sku': b.product.sku_code,
                'product_name': b.product.product_name,
                'quantity_total': str(b.quantity_total),
                'quantity_available': str(b.quantity_available),
                'current_stage': b.current_stage_code,
                'current_location': b.current_location.location_code if b.current_location else None,
                'updated_at': b.updated_at.isoformat() if b.updated_at else None,
            }
            for b in batches
        ]
        return Response(data)

    serializer = BatchCreateSerializer(data=request.data)
    if serializer.is_valid():
        d = serializer.validated_data
        product = Product.objects.get(sku_code=d['product_sku'])

        location = None
        if d.get('location_code'):
            location = StorageLocation.objects.get(location_code=d['location_code'])

        batch = Batch.objects.create(
            batch_number=d['batch_number'],
            product=product,
            quantity_total=d['quantity'],
            current_stage_code='expected',
            current_location=location,
        )

        return Response(
            {
                'batch_id': batch.batch_id,
                'batch_number': batch.batch_number,
                'status': 'created',
            },
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
def order_list_create(request):
    """
    GET  /api/v1/orders/ — список заказов
    POST /api/v1/orders/ — создание заказа
    """
    if request.method == 'GET':
        orders = CustomerOrder.objects.all()
        data = [
            {
                'order_id': o.order_id,
                'order_number': o.order_number,
                'priority': o.priority_code,
                'current_stage': o.current_stage_code,
                'completion_percent': str(o.completion_percent),
                'planned_ship_date': o.planned_ship_date.isoformat() if o.planned_ship_date else None,
                'created_at': o.created_at.isoformat(),
            }
            for o in orders
        ]
        return Response(data)

    serializer = OrderCreateSerializer(data=request.data)
    if serializer.is_valid():
        d = serializer.validated_data

        order = CustomerOrder.objects.create(
            order_number=d['order_number'],
            priority_code=d['priority'],
            planned_ship_date=d.get('planned_ship_date'),
            current_stage_code='created',
        )

        for item in d['items']:
            product = Product.objects.get(sku_code=item['product_sku'])
            OrderLine.objects.create(
                order=order,
                product=product,
                requested_qty=item['quantity'],
            )

        return Response(
            {
                'order_id': order.order_id,
                'order_number': order.order_number,
                'status': 'created',
                'lines_count': order.lines.count(),
            },
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
