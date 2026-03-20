"""
Сервис обработки событий цифрового двойника.

Принимает валидированные данные события, сохраняет в журнал ProcessEvent
и обновляет текущее состояние объектов (Batch, CustomerOrder).

Это ядро системы — модуль приёма и регистрации событий +
модуль управления состоянием цифрового двойника (из архитектуры).
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


class EventProcessor:
    """
    Основной сервис обработки входящих событий.

    Порядок работы:
        1. Создаёт запись ProcessEvent в журнале (статус 'received')
        2. Вызывает обработчик по event_type
        3. Обработчик обновляет состояние объектов (Batch / CustomerOrder)
        4. Обновляет статус ProcessEvent → 'applied' или 'rejected'
    """

    # Маппинг event_type → метод-обработчик
    HANDLERS = {
        'batch.received': '_handle_batch_received',
        'batch.placed': '_handle_batch_placed',
        'batch.moved': '_handle_batch_moved',
        'batch.reserved': '_handle_batch_reserved',
        'order.created': '_handle_order_created',
        'order.picking_started': '_handle_order_picking_started',
        'order.item_picked': '_handle_order_item_picked',
        'order.assembled': '_handle_order_assembled',
        'shipment.dispatched': '_handle_shipment_dispatched',
        'location.blocked': '_handle_location_blocked',
        'location.unblocked': '_handle_location_unblocked',
    }

    @transaction.atomic
    def process_event(self, validated_data: dict) -> dict:
        """
        Основная точка входа — обработка одного события.

        Args:
            validated_data: Валидированные данные из EventSerializer.

        Returns:
            dict с результатом: status, event_id, processing_result, message.
        """
        event_type = validated_data['event_type']
        external_id = validated_data['event_id']

        # 1. Создаём запись в журнале
        event = ProcessEvent.objects.create(
            external_event_id=external_id,
            event_type_code=event_type,
            source_system=validated_data['source_system'],
            event_time=validated_data['occurred_at'],
            processing_status='received',
            payload_json=validated_data.get('payload', {}),
        )

        # 2. Вызываем обработчик
        handler_name = self.HANDLERS.get(event_type)
        if not handler_name:
            event.processing_status = 'rejected'
            event.save(update_fields=['processing_status'])
            return {
                'status': 'rejected',
                'event_id': external_id,
                'processing_result': 'unknown_event_type',
                'message': f'Неизвестный тип события: {event_type}',
            }

        try:
            handler = getattr(self, handler_name)
            handler(event, validated_data)

            # 3. Успех — обновляем статус
            event.processing_status = 'applied'
            event.save(update_fields=['processing_status'])

            logger.info(f'Event {external_id} ({event_type}) applied successfully')
            return {
                'status': 'accepted',
                'event_id': external_id,
                'processing_result': 'projection_updated',
                'message': 'Event accepted and applied successfully',
            }

        except EventProcessingError as e:
            event.processing_status = 'rejected'
            event.save(update_fields=['processing_status'])
            logger.warning(f'Event {external_id} rejected: {e}')
            return {
                'status': 'rejected',
                'event_id': external_id,
                'processing_result': 'validation_failed',
                'message': str(e),
            }

        except Exception as e:
            event.processing_status = 'rejected'
            event.save(update_fields=['processing_status'])
            logger.exception(f'Event {external_id} error: {e}')
            return {
                'status': 'error',
                'event_id': external_id,
                'processing_result': 'internal_error',
                'message': f'Внутренняя ошибка обработки: {str(e)}',
            }

    # -----------------------------------------------------------------------
    # Обработчики событий партий (batch.*)
    # -----------------------------------------------------------------------

    def _handle_batch_received(self, event: ProcessEvent, data: dict):
        """
        Партия принята на склад.

        Создаёт новую партию или обновляет существующую.
        Статус → received.
        """
        payload = data['payload']
        batch_code = payload.get('batch_code', data['object_id'])
        product_sku = payload.get('product_sku')
        qty = Decimal(str(payload.get('qty', 0)))

        if not product_sku:
            raise EventProcessingError('payload.product_sku обязателен для batch.received')

        product = Product.objects.filter(sku_code=product_sku).first()
        if not product:
            raise EventProcessingError(f'Товар с SKU "{product_sku}" не найден')

        # Ищем локацию приёмки, если указана
        location = None
        receiving_gate = payload.get('receiving_gate')
        if receiving_gate:
            location = StorageLocation.objects.filter(location_code=receiving_gate).first()

        batch, created = Batch.objects.update_or_create(
            batch_number=batch_code,
            defaults={
                'product': product,
                'quantity_total': qty,
                'current_stage_code': 'received',
                'current_location': location,
                'receipt_date': data['occurred_at'],
                'last_event': event,
            },
        )

        event.batch = batch
        event.new_stage_code = 'received'
        event.location = location
        event.save(update_fields=['batch', 'new_stage_code', 'location'])

    def _handle_batch_placed(self, event: ProcessEvent, data: dict):
        """
        Партия размещена в ячейке.

        Обновляет текущую локацию партии. Статус → placed или stored.
        """
        payload = data['payload']
        batch_code = payload.get('batch_code', data['object_id'])
        to_location_code = payload.get('to_location')

        if not to_location_code:
            raise EventProcessingError('payload.to_location обязателен для batch.placed')

        batch = self._get_batch(batch_code)
        location = self._get_location(to_location_code)

        # Определяем статус: если зона хранения → stored, иначе placed
        new_stage = 'stored' if location.location_type == 'storage' else 'placed'

        batch.current_location = location
        batch.current_stage_code = new_stage
        batch.last_event = event
        batch.save(update_fields=[
            'current_location', 'current_stage_code', 'last_event', 'updated_at',
        ])

        event.batch = batch
        event.location = location
        event.new_stage_code = new_stage
        event.save(update_fields=['batch', 'location', 'new_stage_code'])

    def _handle_batch_moved(self, event: ProcessEvent, data: dict):
        """
        Партия перемещена между ячейками.

        Обновляет текущую локацию партии.
        """
        payload = data['payload']
        batch_code = payload.get('batch_code', data['object_id'])
        to_location_code = payload.get('to_location')

        if not to_location_code:
            raise EventProcessingError('payload.to_location обязателен для batch.moved')

        batch = self._get_batch(batch_code)
        location = self._get_location(to_location_code)

        batch.current_location = location
        batch.last_event = event
        batch.save(update_fields=['current_location', 'last_event', 'updated_at'])

        event.batch = batch
        event.location = location
        event.save(update_fields=['batch', 'location'])

    def _handle_batch_reserved(self, event: ProcessEvent, data: dict):
        """
        Количество партии зарезервировано под заказ.

        Создаёт BatchReservation, увеличивает quantity_reserved.
        Статус → reserved (если ещё не в более позднем этапе).
        """
        payload = data['payload']
        batch_code = payload.get('batch_code', data['object_id'])
        order_number = payload.get('order_number')
        qty_reserved = Decimal(str(payload.get('qty_reserved', 0)))

        if not order_number:
            raise EventProcessingError('payload.order_number обязателен для batch.reserved')
        if qty_reserved <= 0:
            raise EventProcessingError('payload.qty_reserved должен быть больше 0')

        batch = self._get_batch(batch_code)
        order = CustomerOrder.objects.filter(order_number=order_number).first()
        if not order:
            raise EventProcessingError(f'Заказ "{order_number}" не найден')

        # Проверяем доступное количество
        if batch.quantity_available < qty_reserved:
            raise EventProcessingError(
                f'Недостаточно товара: доступно {batch.quantity_available}, '
                f'запрошено {qty_reserved}'
            )

        # Ищем подходящую строку заказа по товару
        order_line = OrderLine.objects.filter(
            order=order,
            product=batch.product,
        ).first()
        if not order_line:
            raise EventProcessingError(
                f'В заказе "{order_number}" нет позиции с товаром {batch.product.sku_code}'
            )

        # Создаём резервирование
        BatchReservation.objects.create(
            batch=batch,
            order_line=order_line,
            reserved_qty=qty_reserved,
            reservation_status='active',
        )

        # Обновляем партию
        batch.quantity_reserved += qty_reserved
        batch.current_stage_code = 'reserved'
        batch.last_event = event
        batch.save(update_fields=[
            'quantity_reserved', 'current_stage_code', 'last_event', 'updated_at',
        ])

        event.batch = batch
        event.order = order
        event.new_stage_code = 'reserved'
        event.save(update_fields=['batch', 'order', 'new_stage_code'])

    # -----------------------------------------------------------------------
    # Обработчики событий заказов (order.*)
    # -----------------------------------------------------------------------

    def _handle_order_created(self, event: ProcessEvent, data: dict):
        """
        Заказ создан.

        Создаёт CustomerOrder и его строки OrderLine.
        """
        payload = data['payload']
        order_number = payload.get('order_number', data['object_id'])
        priority = payload.get('priority', 'normal')
        planned_ship_at = payload.get('planned_ship_at')
        items = payload.get('items', [])

        if CustomerOrder.objects.filter(order_number=order_number).exists():
            raise EventProcessingError(f'Заказ "{order_number}" уже существует')

        order = CustomerOrder.objects.create(
            order_number=order_number,
            priority_code=priority,
            planned_ship_date=planned_ship_at,
            current_stage_code='created',
            last_event=event,
        )

        # Создаём строки заказа
        for item in items:
            product_sku = item.get('product_sku')
            qty = Decimal(str(item.get('qty_requested', item.get('quantity', 0))))

            product = Product.objects.filter(sku_code=product_sku).first()
            if not product:
                raise EventProcessingError(
                    f'Товар с SKU "{product_sku}" не найден при создании строки заказа'
                )

            OrderLine.objects.create(
                order=order,
                product=product,
                requested_qty=qty,
            )

        event.order = order
        event.new_stage_code = 'created'
        event.save(update_fields=['order', 'new_stage_code'])

    def _handle_order_picking_started(self, event: ProcessEvent, data: dict):
        """
        Начата комплектация заказа.

        Статус заказа → picking.
        """
        payload = data['payload']
        order_number = payload.get('order_number', data['object_id'])

        order = self._get_order(order_number)
        order.current_stage_code = 'picking'
        order.last_event = event
        order.save(update_fields=['current_stage_code', 'last_event', 'updated_at'])

        event.order = order
        event.new_stage_code = 'picking'
        event.save(update_fields=['order', 'new_stage_code'])

    def _handle_order_item_picked(self, event: ProcessEvent, data: dict):
        """
        Позиция заказа подобрана.

        Увеличивает picked_qty в резервировании, обновляет completion_percent.
        """
        payload = data['payload']
        order_number = payload.get('order_number', data['object_id'])
        product_sku = payload.get('product_sku')
        qty_picked = Decimal(str(payload.get('qty_picked', 0)))
        batch_code = payload.get('batch_code')

        order = self._get_order(order_number)

        # Обновляем резервирование, если указана партия
        if batch_code:
            batch = self._get_batch(batch_code)
            reservation = BatchReservation.objects.filter(
                batch=batch,
                order_line__order=order,
                order_line__product__sku_code=product_sku,
            ).first()

            if reservation:
                reservation.picked_qty += qty_picked
                reservation.reservation_status = 'picking'
                reservation.save(update_fields=['picked_qty', 'reservation_status'])

            # Обновляем партию: подобранное переходит из резерва
            batch.quantity_reserved -= qty_picked
            batch.quantity_picked += qty_picked
            batch.current_stage_code = 'picked'
            batch.last_event = event
            batch.save(update_fields=[
                'quantity_reserved', 'quantity_picked',
                'current_stage_code', 'last_event', 'updated_at',
            ])
            event.batch = batch

        # Пересчитываем completion_percent заказа
        self._recalc_order_completion(order)

        order.last_event = event
        order.save(update_fields=['completion_percent', 'last_event', 'updated_at'])

        event.order = order
        event.save(update_fields=['order', 'batch'])

    def _handle_order_assembled(self, event: ProcessEvent, data: dict):
        """
        Комплектация заказа завершена.

        Статус заказа → assembled, completion_percent → 100.
        """
        payload = data['payload']
        order_number = payload.get('order_number', data['object_id'])

        order = self._get_order(order_number)
        order.current_stage_code = 'assembled'
        order.completion_percent = Decimal('100.00')
        order.last_event = event
        order.save(update_fields=[
            'current_stage_code', 'completion_percent', 'last_event', 'updated_at',
        ])

        event.order = order
        event.new_stage_code = 'assembled'
        event.save(update_fields=['order', 'new_stage_code'])

    # -----------------------------------------------------------------------
    # Обработчик отгрузки (shipment.*)
    # -----------------------------------------------------------------------

    def _handle_shipment_dispatched(self, event: ProcessEvent, data: dict):
        """
        Отгрузка выполнена.

        Закрывает заказ (→ shipped) и обновляет связанные партии.
        """
        payload = data['payload']
        order_number = payload.get('order_number', data['object_id'])

        order = self._get_order(order_number)
        order.current_stage_code = 'shipped'
        order.completion_percent = Decimal('100.00')
        order.last_event = event
        order.save(update_fields=[
            'current_stage_code', 'completion_percent', 'last_event', 'updated_at',
        ])

        # Обновляем статусы резервирований и партий
        reservations = BatchReservation.objects.filter(
            order_line__order=order,
        ).select_related('batch')

        for res in reservations:
            res.reservation_status = 'shipped'
            res.save(update_fields=['reservation_status'])

            batch = res.batch
            # Отгруженное переходит из подобранного
            batch.quantity_picked -= res.picked_qty
            batch.quantity_shipped += res.picked_qty
            batch.current_stage_code = 'shipped'
            batch.last_event = event
            batch.save(update_fields=[
                'quantity_picked', 'quantity_shipped',
                'current_stage_code', 'last_event', 'updated_at',
            ])

        event.order = order
        event.new_stage_code = 'shipped'
        event.save(update_fields=['order', 'new_stage_code'])

    # -----------------------------------------------------------------------
    # Обработчики локаций (location.*)
    # -----------------------------------------------------------------------

    def _handle_location_blocked(self, event: ProcessEvent, data: dict):
        """Блокировка ячейки."""
        payload = data['payload']
        location_code = payload.get('location_code', data['object_id'])
        location = self._get_location(location_code)

        event.location = location
        event.save(update_fields=['location'])

    def _handle_location_unblocked(self, event: ProcessEvent, data: dict):
        """Разблокировка ячейки."""
        payload = data['payload']
        location_code = payload.get('location_code', data['object_id'])
        location = self._get_location(location_code)

        event.location = location
        event.save(update_fields=['location'])

    # -----------------------------------------------------------------------
    # Вспомогательные методы
    # -----------------------------------------------------------------------

    def _get_batch(self, batch_code: str) -> Batch:
        batch = Batch.objects.filter(batch_number=batch_code).first()
        if not batch:
            raise EventProcessingError(f'Партия "{batch_code}" не найдена')
        return batch

    def _get_order(self, order_number: str) -> CustomerOrder:
        order = CustomerOrder.objects.filter(order_number=order_number).first()
        if not order:
            raise EventProcessingError(f'Заказ "{order_number}" не найден')
        return order

    def _get_location(self, location_code: str) -> StorageLocation:
        location = StorageLocation.objects.filter(location_code=location_code).first()
        if not location:
            raise EventProcessingError(f'Локация "{location_code}" не найдена')
        return location

    def _recalc_order_completion(self, order: CustomerOrder):
        """Пересчитывает процент выполнения заказа по строкам."""
        lines = order.lines.all()
        if not lines.exists():
            return

        total_requested = sum(line.requested_qty for line in lines)
        if total_requested == 0:
            return

        total_picked = Decimal('0')
        for line in lines:
            picked = line.reservations.aggregate(
                total=models.Sum('picked_qty')
            )['total'] or Decimal('0')
            total_picked += picked

        order.completion_percent = min(
            (total_picked / total_requested * 100).quantize(Decimal('0.01')),
            Decimal('100.00'),
        )
