"""
Модели складского учёта: Batch, BatchReservation.

Batch — партия товара, центральный объект цифрового двойника.
    Хранит текущее состояние прямо в себе (вместо отдельной BatchCurrentState).

BatchReservation — резервирование партии под строку заказа.
    Связующая сущность между Batch и OrderLine (M:M через промежуточную таблицу).
"""

from django.db import models


class Batch(models.Model):
    """
    Партия товара — основной объект наблюдения цифрового двойника.

    Проходит этапы: expected → received → placed → stored → reserved →
    picked → shipped → closed.

    Текущее состояние (этап, локация, количества) встроено прямо в сущность
    для упрощения MVP — вместо отдельной таблицы BatchCurrentState.

    Связи:
        Batch M:1 Product
        Batch M:1 StorageLocation (nullable — текущая локация)
        Batch 1:M BatchReservation
        Batch 1:M ProcessEvent
    """

    STAGE_CHOICES = [
        ('expected', 'Ожидает приёмки'),
        ('received', 'Принята'),
        ('placed', 'Размещена'),
        ('stored', 'На хранении'),
        ('reserved', 'Зарезервирована'),
        ('shipped', 'Отгружена'),
    ]

    batch_id = models.BigAutoField(
        primary_key=True,
        verbose_name='ID партии',
    )
    batch_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Номер партии',
        help_text='Уникальный номер партии, например: BATCH-00045',
    )
    product = models.ForeignKey(
        'references.Product',
        on_delete=models.PROTECT,
        related_name='batches',
        verbose_name='Товар',
    )
    quantity_total = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        verbose_name='Общее количество',
    )
    quantity_reserved = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Зарезервировано',
    )
    quantity_picked = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Подобрано',
    )
    quantity_shipped = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Отгружено',
    )

    # --- Текущее состояние (встроено в Batch для MVP) ---
    current_stage_code = models.CharField(
        max_length=50,
        choices=STAGE_CHOICES,
        default='expected',
        verbose_name='Текущий этап',
    )
    current_location = models.ForeignKey(
        'references.StorageLocation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='batches',
        verbose_name='Текущая локация',
    )
    last_event = models.ForeignKey(
        'events.ProcessEvent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Последнее событие',
    )
    receipt_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата поступления',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата последнего обновления',
    )

    class Meta:
        db_table = 'batch'
        verbose_name = 'Партия'
        verbose_name_plural = 'Партии'
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.batch_number} [{self.get_current_stage_code_display()}]'

    @property
    def quantity_available(self):
        """Доступное количество = общее − зарезервированное − подобранное − отгруженное."""
        return self.quantity_total - self.quantity_reserved - self.quantity_picked - self.quantity_shipped


class BatchReservation(models.Model):
    """
    Резервирование партии под строку заказа.

    Фиксирует, какая партия и в каком объёме зарезервирована
    под конкретную строку заказа. Позволяет реализовать связь M:M
    между партиями и строками заказа.

    Связи:
        BatchReservation M:1 Batch
        BatchReservation M:1 OrderLine
    """

    RESERVATION_STATUS_CHOICES = [
        ('active', 'Активно'),
        ('picking', 'В комплектации'),
        ('picked', 'Подобрано'),
        ('shipped', 'Отгружено'),
        ('cancelled', 'Отменено'),
    ]

    reservation_id = models.BigAutoField(
        primary_key=True,
        verbose_name='ID резервирования',
    )
    batch = models.ForeignKey(
        'inventory.Batch',
        on_delete=models.PROTECT,
        related_name='reservations',
        verbose_name='Партия',
    )
    order_line = models.ForeignKey(
        'orders.OrderLine',
        on_delete=models.PROTECT,
        related_name='reservations',
        verbose_name='Строка заказа',
    )
    reserved_qty = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        verbose_name='Зарезервировано',
    )
    picked_qty = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Подобрано',
    )
    reservation_status = models.CharField(
        max_length=30,
        choices=RESERVATION_STATUS_CHOICES,
        default='active',
        verbose_name='Статус резервирования',
    )

    class Meta:
        db_table = 'batch_reservation'
        verbose_name = 'Резервирование партии'
        verbose_name_plural = 'Резервирования партий'

    def __str__(self):
        return f'Резерв {self.batch} → {self.order_line} ({self.reserved_qty})'
