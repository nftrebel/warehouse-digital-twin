"""
Сериализаторы REST API.

Отвечают за валидацию входящих данных POST-запросов:
- EventSerializer — основной приём событий
- BulkEventSerializer — пакетная загрузка событий
- ProductSerializer — создание товара
- StorageLocationSerializer — создание локации
- BatchCreateSerializer — создание партии
- OrderCreateSerializer — создание заказа
"""

from rest_framework import serializers
from apps.references.models import Product, StorageLocation
from apps.inventory.models import Batch
from apps.orders.models import CustomerOrder, OrderLine
from apps.events.models import ProcessEvent


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

class ProductSerializer(serializers.ModelSerializer):
    """Создание / чтение товара."""

    class Meta:
        model = Product
        fields = ['product_id', 'sku_code', 'product_name', 'unit_of_measure']
        read_only_fields = ['product_id']


class StorageLocationSerializer(serializers.ModelSerializer):
    """Создание / чтение складской локации."""

    class Meta:
        model = StorageLocation
        fields = ['location_id', 'location_code', 'location_name', 'location_type']
        read_only_fields = ['location_id']


# ---------------------------------------------------------------------------
# Партии
# ---------------------------------------------------------------------------

class BatchCreateSerializer(serializers.Serializer):
    """
    Ручное создание стартовой партии для демонстрации.

    Используется через POST /api/v1/batches/.
    """

    batch_number = serializers.CharField(max_length=50)
    product_sku = serializers.CharField(max_length=50)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    location_code = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def validate_product_sku(self, value):
        if not Product.objects.filter(sku_code=value).exists():
            raise serializers.ValidationError(
                f'Товар с SKU "{value}" не найден. Сначала создайте товар.'
            )
        return value

    def validate_batch_number(self, value):
        if Batch.objects.filter(batch_number=value).exists():
            raise serializers.ValidationError(
                f'Партия с номером "{value}" уже существует.'
            )
        return value

    def validate_location_code(self, value):
        if value and not StorageLocation.objects.filter(location_code=value).exists():
            raise serializers.ValidationError(
                f'Локация с кодом "{value}" не найдена.'
            )
        return value


# ---------------------------------------------------------------------------
# Заказы
# ---------------------------------------------------------------------------

class OrderLineCreateSerializer(serializers.Serializer):
    """Строка заказа при создании заказа."""

    product_sku = serializers.CharField(max_length=50)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)

    def validate_product_sku(self, value):
        if not Product.objects.filter(sku_code=value).exists():
            raise serializers.ValidationError(
                f'Товар с SKU "{value}" не найден.'
            )
        return value


class OrderCreateSerializer(serializers.Serializer):
    """
    Ручное создание заказа для демонстрации.

    Используется через POST /api/v1/orders/.
    """

    order_number = serializers.CharField(max_length=50)
    priority = serializers.ChoiceField(
        choices=['low', 'normal', 'high', 'urgent'],
        default='normal',
    )
    planned_ship_date = serializers.DateTimeField(required=False, allow_null=True)
    items = OrderLineCreateSerializer(many=True, min_length=1)

    def validate_order_number(self, value):
        if CustomerOrder.objects.filter(order_number=value).exists():
            raise serializers.ValidationError(
                f'Заказ с номером "{value}" уже существует.'
            )
        return value


# ---------------------------------------------------------------------------
# События — основной сериализатор
# ---------------------------------------------------------------------------

VALID_EVENT_TYPES = [
    'batch.received',
    'batch.placed',
    'batch.moved',
    'batch.reserved',
    'order.created',
    'order.picking_started',
    'order.item_picked',
    'order.assembled',
    'shipment.dispatched',
    'location.blocked',
    'location.unblocked',
]


class EventSerializer(serializers.Serializer):
    """
    Основной сериализатор для приёма события складского процесса.

    Соответствует структуре POST /api/v1/events/ из ТЗ (раздел 12.2).
    """

    event_id = serializers.CharField(
        max_length=100,
        help_text='Уникальный идентификатор события (UUID) для защиты от дубликатов',
    )
    event_type = serializers.ChoiceField(
        choices=VALID_EVENT_TYPES,
        help_text='Тип события, определяющий бизнес-логику обработки',
    )
    occurred_at = serializers.DateTimeField(
        help_text='Момент фактического возникновения события (ISO 8601)',
    )
    source_system = serializers.CharField(
        max_length=100,
        help_text='Источник: scanner, simulator, import, manual',
    )
    warehouse_code = serializers.CharField(
        max_length=50,
        required=False,
        default='WH-01',
    )
    object_type = serializers.ChoiceField(
        choices=['batch', 'order', 'location', 'shipment'],
        help_text='Тип бизнес-объекта',
    )
    object_id = serializers.CharField(
        max_length=100,
        help_text='Идентификатор объекта в предметной области',
    )
    correlation_id = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    actor = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    payload = serializers.DictField(
        help_text='Полезная нагрузка — зависит от event_type',
    )

    def validate_event_id(self, value):
        """Проверка на дубликат."""
        if ProcessEvent.objects.filter(external_event_id=value).exists():
            raise serializers.ValidationError('__DUPLICATE__')
        return value


class BulkEventSerializer(serializers.Serializer):
    """Пакетная загрузка нескольких событий."""

    events = EventSerializer(many=True)
