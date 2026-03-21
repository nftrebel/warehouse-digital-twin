"""
Сервис цифрового двойника — ядро системы.

Принимает валидированные данные события, сохраняет в журнал
и обновляет текущее состояние объектов (Batch, CustomerOrder, StorageLocation).

Бизнес-правила (раздел 13 ТЗ):
  - Одно и то же событие с одинаковым event_id не применяется дважды.
  - Размещение партии возможно только при существовании ячейки.
  - Списание и отгрузка не уменьшают количество ниже нуля.
  - Заказ не переводится в shipped, пока позиции не укомплектованы.
"""

import logging
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone

from apps.references.models import Product, StorageLocation
from apps.inventory.models import Batch, BatchReservation
from apps.orders.models import CustomerOrder, OrderLine
from apps.events.models import ProcessEvent

logger = logging.getLogger(__name__)


class EventProcessingError(Exception):
    """Ошибка обработки события."""
    pass


class DuplicateEventError(Exception):
    """Событие с таким event_id уже зарегистрировано."""
    pass


class DigitalTwinService:
    """
    Сервис управления состоянием цифрового двойника.

    Основной метод — process_event(data), который:
    1. Проверяет дубликат по external_event_id
    2. Сохраняет событие в журнал (ProcessEvent)
    3. Вызывает обработчик для конкретного event_type
    4. Обновляет текущее состояние объектов
    """

    # Маппинг event_type → метод-обработчик
    EVENT_HANDLERS = {
        'batch.received': '_handle_batch_received',
        'batch.placed': '_handle_batch_placed',
        'batch.moved': '_handle_batch_moved',
        'batch.reserved': '_handle_batch_reserved',
        'order.created': '_handle_order_created',
        'order.picking_started': '_handle_order_picking_started',
        'order.item_picked': '_handle_order_item_picked',
        'order.assembled': '_handle_order_assembled',
        'shipment.dispatched': '_handle_shipment_dispatched',
    }

    @transaction.atomic
    def process_event(self, data: dict) -> dict:
        """
        Главный метод: обработка одного входящего события.

        Args:
            data: валидированные данные из EventIngestSerializer

        Returns:
            dict со статусом обработки

        Raises:
            DuplicateEventError: если событие уже зарегистрировано
            EventProcessingError: если событие не может быть обработано
        """
        external_id = data['event_id']
        event_type = data['event_type']

        # 1. Проверка дубликата
        if ProcessEvent.objects.filter(external_event_id=external_id).exists():
            raise DuplicateEventError(
                f'Событие с event_id="{external_id}" уже зарегистрировано.'
            )

        # 2. Создаём запись в журнале
        event = ProcessEvent.objects.create(
            external_event_id=external_id,
            event_type_code=event_type,
            source_system=data['source_system'],
            event_time=data['occurred_at'],
            payload_json=data.get('payload', {}),
            processing_status='received',
        )

        # 3. Вызываем обработчик
        handler_name = self.EVENT_HANDLERS.get(event_type)
        if not handler_name:
            event.processing_status = 'rejected'
            event.save(update_fields=['processing_status'])
            raise EventProcessingError(f'Неизвестный тип события: {event_type}')

        try:
            handler = getattr(self, handler_name)
            result = handler(event, data)
            event.processing_status = 'applied'
            event.save(update_fields=['processing_status'])
            return {
                'status': 'accepted',
                'event_id': external_id,
                'processing_result': 'projection_updated',
                'message': result or 'Event accepted and applied successfully',
            }
        except EventProcessingError:
            event.processing_status = 'rejected'
            event.save(update_fields=['processing_status'])
            raise
        except Exception as e:
            event.processing_status = 'rejected'
            event.save(update_fields=['processing_status'])
            logger.exception(f'Ошибка обработки события {external_id}')
            raise EventProcessingError(f'Внутренняя ошибка: {str(e)}')

    # -----------------------------------------------------------------------
    # Обработчики событий партий
    # -----------------------------------------------------------------------

    def _handle_batch_received(self, event: ProcessEvent, data: dict) -> str:
        """
        batch.received — Партия принята на склад.
        Создаёт или обновляет партию, переводит в статус received.
        """
        payload = data.get('payload', {})
        batch_code = payload.get('batch_code', data['object_id'])
        product_sku = payload.get('product_sku')
        qty = Decimal(str(payload.get('qty', 0)))

        if not product_sku:
            raise EventProcessingError('payload.product_sku обязателен для batch.received')
        if qty <= 0:
            raise EventProcessingError('payload.qty должен быть больше нуля')

        product = self._get_product(product_sku)

        batch, created = Batch.objects.get_or_create(
            batch_number=batch_code,
            defaults={
                'product': product,
                'quantity_total': qty,
                'current_stage_code': 'received',
                'receipt_date': data['occurred_at'],
            }
        )

        if not created:
            batch.current_stage_code = 'received'
            batch.quantity_total = qty
            batch.receipt_date = data['occurred_at']

        batch.last_event = event
        batch.save()

        # Привязываем событие к партии
        event.batch = batch
        event.new_stage_code = 'received'
        event.save(update_fields=['batch', 'new_stage_code'])

        action = 'создана' if created else 'обновлена'
        return f'Партия {batch_code} {action}, статус: received'

    def _handle_batch_placed(self, event: ProcessEvent, data: dict) -> str:
        """
        batch.placed — Партия размещена в ячейке.
        Обновляет current_location_id и статус placed/stored.
        """
        payload = data.get('payload', {})
        batch_code = payload.get('batch_code', data['object_id'])
        to_location_code = payload.get('to_location')

        if not to_location_code:
            raise EventProcessingError('payload.to_location обязателен для batch.placed')

        batch = self._get_batch(batch_code)
        location = self._get_location(to_location_code)

        batch.current_location = location
        batch.current_stage_code = 'placed'
        batch.last_event = event
        batch.save()

        event.batch = batch
        event.location = location
        event.new_stage_code = 'placed'
        event.save(update_fields=['batch', 'location', 'new_stage_code'])

        return f'Партия {batch_code} размещена в {to_location_code}'

    def _handle_batch_moved(self, event: ProcessEvent, data: dict) -> str:
        """
        batch.moved — Партия перемещена между ячейками.
        """
        payload = data.get('payload', {})
        batch_code = payload.get('batch_code', data['object_id'])
        to_location_code = payload.get('to_location')

        if not to_location_code:
            raise EventProcessingError('payload.to_location обязателен для batch.moved')

        batch = self._get_batch(batch_code)
        location = self._get_location(to_location_code)

        batch.current_location = location
        batch.current_stage_code = 'stored'
        batch.last_event = event
        batch.save()

        event.batch = batch
        event.location = location
        event.new_stage_code = 'stored'
        event.save(update_fields=['batch', 'location', 'new_stage_code'])

        return f'Партия {batch_code} перемещена в {to_location_code}'

    def _handle_batch_reserved(self, event: ProcessEvent, data: dict) -> str:
        """
        batch.reserved — Количество партии зарезервировано под заказ.
        Связывает партию с заказом, уменьшает доступный остаток.
        """
        payload = data.get('payload', {})
        batch_code = payload.get('batch_code', data['object_id'])
        order_number = payload.get('order_number')
        qty_reserved = Decimal(str(payload.get('qty_reserved', 0)))

        if not order_number:
            raise EventProcessingError('payload.order_number обязателен для batch.reserved')
        if qty_reserved <= 0:
            raise EventProcessingError('payload.qty_reserved должен быть больше нуля')

        batch = self._get_batch(batch_code)
        order = self._get_order(order_number)

        # Проверяем доступное количество
        if batch.quantity_available < qty_reserved:
            raise EventProcessingError(
                f'Недостаточно доступного количества в партии {batch_code}: '
                f'доступно {batch.quantity_available}, запрошено {qty_reserved}'
            )

        # Ищем подходящую строку заказа (первую с тем же товаром)
        order_line = OrderLine.objects.filter(
            order=order, product=batch.product
        ).first()

        if not order_line:
            raise EventProcessingError(
                f'В заказе {order_number} нет позиции с товаром {batch.product.sku_code}'
            )

        # Создаём резервирование
        BatchReservation.objects.create(
            batch=batch,
            order_line=order_line,
            reserved_qty=qty_reserved,
            reservation_status='active',
        )

        batch.quantity_reserved += qty_reserved
        batch.current_stage_code = 'reserved'
        batch.last_event = event
        batch.save()

        event.batch = batch
        event.order = order
        event.new_stage_code = 'reserved'
        event.save(update_fields=['batch', 'order', 'new_stage_code'])

        return f'Партия {batch_code}: зарезервировано {qty_reserved} под заказ {order_number}'

    # -----------------------------------------------------------------------
    # Обработчики событий заказов
    # -----------------------------------------------------------------------

    def _handle_order_created(self, event: ProcessEvent, data: dict) -> str:
        """
        order.created — Поступил заказ на отгрузку.
        Создаёт заказ и его строки.
        """
        payload = data.get('payload', {})
        order_number = payload.get('order_number', data['object_id'])
        priority = payload.get('priority', 'normal')
        planned_ship_at = payload.get('planned_ship_at')
        items = payload.get('items', [])

        if CustomerOrder.objects.filter(order_number=order_number).exists():
            raise EventProcessingError(f'Заказ {order_number} уже существует')

        order = CustomerOrder.objects.create(
            order_number=order_number,
            priority_code=priority,
            planned_ship_date=planned_ship_at,
            current_stage_code='created',
            last_event=event,
        )

        for item in items:
            product_sku = item.get('product_sku')
            qty = Decimal(str(item.get('qty', 0)))
            if product_sku and qty > 0:
                product = self._get_product(product_sku)
                OrderLine.objects.create(
                    order=order,
                    product=product,
                    requested_qty=qty,
                )

        event.order = order
        event.new_stage_code = 'created'
        event.save(update_fields=['order', 'new_stage_code'])

        return f'Заказ {order_number} создан с {len(items)} позициями'

    def _handle_order_picking_started(self, event: ProcessEvent, data: dict) -> str:
        """
        order.picking_started — Начата комплектация заказа.
        """
        payload = data.get('payload', {})
        order_number = payload.get('order_number', data['object_id'])

        order = self._get_order(order_number)
        order.current_stage_code = 'picking'
        order.last_event = event
        order.save()

        # Обновляем статус резервирований
        BatchReservation.objects.filter(
            order_line__order=order,
            reservation_status='active',
        ).update(reservation_status='picking')

        event.order = order
        event.new_stage_code = 'picking'
        event.save(update_fields=['order', 'new_stage_code'])

        return f'Комплектация заказа {order_number} начата'

    def _handle_order_item_picked(self, event: ProcessEvent, data: dict) -> str:
        """
        order.item_picked — Отобрана позиция заказа.
        Увеличивает qty_picked и обновляет completion_percent.
        """
        payload = data.get('payload', {})
        order_number = payload.get('order_number', data['object_id'])
        product_sku = payload.get('product_sku')
        qty_picked = Decimal(str(payload.get('qty_picked', 0)))
        batch_code = payload.get('batch_code')

        if not product_sku:
            raise EventProcessingError('payload.product_sku обязателен для order.item_picked')

        order = self._get_order(order_number)

        # Если указана партия — обновляем её
        if batch_code:
            batch = self._get_batch(batch_code)
            batch.quantity_reserved -= qty_picked
            batch.quantity_picked += qty_picked
            batch.last_event = event
            batch.save()
            event.batch = batch

            # Обновляем резервирование
            reservation = BatchReservation.objects.filter(
                batch=batch,
                order_line__order=order,
                order_line__product__sku_code=product_sku,
            ).first()
            if reservation:
                reservation.picked_qty += qty_picked
                reservation.reservation_status = 'picked'
                reservation.save()

        # Пересчитываем процент выполнения заказа
        self._recalculate_order_completion(order)

        order.last_event = event
        order.save()

        event.order = order
        event.new_stage_code = 'picking'
        event.save(update_fields=['batch', 'order', 'new_stage_code'])

        return f'Заказ {order_number}: подобрано {qty_picked} × {product_sku}'

    def _handle_order_assembled(self, event: ProcessEvent, data: dict) -> str:
        """
        order.assembled — Комплектация заказа завершена.
        """
        payload = data.get('payload', {})
        order_number = payload.get('order_number', data['object_id'])

        order = self._get_order(order_number)
        order.current_stage_code = 'assembled'
        order.completion_percent = Decimal('100.00')
        order.last_event = event
        order.save()

        event.order = order
        event.new_stage_code = 'assembled'
        event.save(update_fields=['order', 'new_stage_code'])

        return f'Заказ {order_number} скомплектован'

    # -----------------------------------------------------------------------
    # Обработчики событий отгрузки
    # -----------------------------------------------------------------------

    def _handle_shipment_dispatched(self, event: ProcessEvent, data: dict) -> str:
        """
        shipment.dispatched — Заказ отгружен.
        Партии: если товар остался → stored, если нет → shipped.
        """
        payload = data.get('payload', {})
        order_number = payload.get('order_number', data['object_id'])

        order = self._get_order(order_number)

        if order.current_stage_code not in ('assembled', 'picking', 'shipped'):
            raise EventProcessingError(
                f'Заказ {order_number} не готов к отгрузке '
                f'(текущий этап: {order.current_stage_code})'
            )

        order.current_stage_code = 'shipped'
        order.last_event = event
        order.save()

        reservations = BatchReservation.objects.filter(
            order_line__order=order,
        ).select_related('batch')

        for reservation in reservations:
            batch = reservation.batch
            batch.quantity_picked -= reservation.picked_qty
            batch.quantity_shipped += reservation.picked_qty
            batch.last_event = event

            # Определяем новый статус партии
            if batch.quantity_available <= 0 and batch.quantity_reserved <= 0 and batch.quantity_picked <= 0:
                batch.current_stage_code = 'shipped'
            elif batch.quantity_reserved > 0:
                batch.current_stage_code = 'reserved'
            else:
                batch.current_stage_code = 'stored'

            batch.save()

            reservation.reservation_status = 'shipped'
            reservation.save()

        event.order = order
        event.new_stage_code = 'shipped'
        event.save(update_fields=['order', 'new_stage_code'])

        return f'Заказ {order_number} отгружен'

    # -----------------------------------------------------------------------
    # Вспомогательные методы
    # -----------------------------------------------------------------------

    def _get_product(self, sku_code: str) -> Product:
        try:
            return Product.objects.get(sku_code=sku_code)
        except Product.DoesNotExist:
            raise EventProcessingError(f'Товар с SKU "{sku_code}" не найден')

    def _get_batch(self, batch_code: str) -> Batch:
        try:
            return Batch.objects.get(batch_number=batch_code)
        except Batch.DoesNotExist:
            raise EventProcessingError(f'Партия "{batch_code}" не найдена')

    def _get_order(self, order_number: str) -> CustomerOrder:
        try:
            return CustomerOrder.objects.get(order_number=order_number)
        except CustomerOrder.DoesNotExist:
            raise EventProcessingError(f'Заказ "{order_number}" не найден')

    def _get_location(self, location_code: str) -> StorageLocation:
        try:
            return StorageLocation.objects.get(location_code=location_code)
        except StorageLocation.DoesNotExist:
            raise EventProcessingError(f'Локация "{location_code}" не найдена')

    def _recalculate_order_completion(self, order: CustomerOrder):
        """Пересчитать процент выполнения заказа."""
        lines = order.lines.all()
        if not lines.exists():
            order.completion_percent = Decimal('0')
            return

        total_requested = Decimal('0')
        total_picked = Decimal('0')

        for line in lines:
            total_requested += line.requested_qty
            picked = line.reservations.aggregate(
                total=models.Sum('picked_qty')
            )['total'] or Decimal('0')
            total_picked += picked

        if total_requested > 0:
            percent = (total_picked / total_requested) * 100
            order.completion_percent = min(percent, Decimal('100.00'))
        else:
            order.completion_percent = Decimal('0')


# Синглтон-экземпляр сервиса
digital_twin_service = DigitalTwinService()
