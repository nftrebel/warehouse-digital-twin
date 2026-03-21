"""
Модель журнала событий: ProcessEvent.

ProcessEvent — главная сущность цифрового двойника.
Каждое событие складского процесса записывается в журнал как неизменяемая запись.
На основании событий восстанавливается текущее состояние партий и заказов.
"""

from django.db import models


class ProcessEvent(models.Model):
    """
    Событие складского процесса.

    Фиксирует факт изменения состояния бизнес-объекта (партии, заказа, локации).
    Является неизменяемой записью журнала событий.

    Тип события и источник хранятся кодом/строкой (без отдельных справочников
    EventType и EventSource — упрощение для MVP).

    Связи:
        ProcessEvent M:1 Batch          (nullable)
        ProcessEvent M:1 CustomerOrder  (nullable)
        ProcessEvent M:1 StorageLocation (nullable)
    """

    EVENT_TYPE_CHOICES = [
        ('batch.received', 'Партия принята на склад'),
        ('batch.placed', 'Партия размещена в ячейке'),
        ('batch.moved', 'Партия перемещена'),
        ('batch.reserved', 'Партия зарезервирована'),
        ('order.created', 'Заказ создан'),
        ('order.picking_started', 'Начата комплектация'),
        ('order.item_picked', 'Позиция подобрана'),
        ('order.assembled', 'Комплектация завершена'),
        ('shipment.dispatched', 'Отгрузка выполнена'),
    ]

    PROCESSING_STATUS_CHOICES = [
        ('received', 'Получено'),
        ('accepted', 'Принято'),
        ('rejected', 'Отклонено'),
        ('applied', 'Применено'),
    ]

    event_id = models.BigAutoField(
        primary_key=True,
        verbose_name='ID события',
    )
    external_event_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        verbose_name='Внешний ID события',
        help_text='UUID из внешней системы — для защиты от дубликатов',
    )
    event_type_code = models.CharField(
        max_length=50,
        choices=EVENT_TYPE_CHOICES,
        verbose_name='Тип события',
    )
    source_system = models.CharField(
        max_length=100,
        verbose_name='Источник события',
        help_text='Например: scanner, simulator, import, manual',
    )
    event_time = models.DateTimeField(
        verbose_name='Время возникновения события',
        help_text='Момент фактического возникновения события в процессе',
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Время получения системой',
    )

    # --- Ссылки на объекты (все nullable) ---
    batch = models.ForeignKey(
        'inventory.Batch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events',
        verbose_name='Партия',
    )
    order = models.ForeignKey(
        'orders.CustomerOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events',
        verbose_name='Заказ',
    )
    location = models.ForeignKey(
        'references.StorageLocation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events',
        verbose_name='Локация',
    )

    new_stage_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name='Новый этап объекта',
        help_text='Код этапа, в который перешёл объект после события',
    )
    processing_status = models.CharField(
        max_length=30,
        choices=PROCESSING_STATUS_CHOICES,
        default='received',
        verbose_name='Статус обработки',
    )
    payload_json = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Полезная нагрузка (JSON)',
        help_text='Дополнительные атрибуты события, зависящие от event_type',
    )

    class Meta:
        db_table = 'process_event'
        verbose_name = 'Событие процесса'
        verbose_name_plural = 'События процесса'
        ordering = ['-event_time']
        indexes = [
            models.Index(fields=['event_type_code'], name='idx_event_type'),
            models.Index(fields=['event_time'], name='idx_event_time'),
            models.Index(fields=['batch'], name='idx_event_batch'),
            models.Index(fields=['order'], name='idx_event_order'),
            models.Index(fields=['processing_status'], name='idx_event_status'),
        ]

    def __str__(self):
        return f'[{self.event_type_code}] {self.event_time:%Y-%m-%d %H:%M} — {self.processing_status}'
