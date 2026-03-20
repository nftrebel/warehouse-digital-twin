"""
Модели заказов: CustomerOrder, OrderLine.

CustomerOrder — заказ на отгрузку с встроенным текущим состоянием.
OrderLine — строка заказа (товарная позиция в составе заказа).
"""

from django.db import models


class CustomerOrder(models.Model):
    """
    Заказ на отгрузку.

    Проходит этапы: created → queued → picking → assembled → shipped →
    closed / cancelled.

    Текущее состояние встроено прямо в сущность (вместо отдельной OrderCurrentState).

    Связи:
        CustomerOrder 1:M OrderLine
        CustomerOrder 1:M ProcessEvent
    """

    STAGE_CHOICES = [
        ('created', 'Создан'),
        ('picking', 'Комплектация'),
        ('assembled', 'Скомплектован'),
        ('shipped', 'Отгружен'),
        ('cancelled', 'Отменён'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Низкий'),
        ('normal', 'Обычный'),
        ('high', 'Высокий'),
        ('urgent', 'Срочный'),
    ]

    order_id = models.BigAutoField(
        primary_key=True,
        verbose_name='ID заказа',
    )
    order_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Номер заказа',
        help_text='Уникальный номер заказа, например: ORD-2026-0001',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания',
    )
    planned_ship_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Плановая дата отгрузки',
    )
    priority_code = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='normal',
        verbose_name='Приоритет',
    )

    # --- Текущее состояние (встроено в CustomerOrder для MVP) ---
    current_stage_code = models.CharField(
        max_length=50,
        choices=STAGE_CHOICES,
        default='created',
        verbose_name='Текущий этап',
    )
    last_event = models.ForeignKey(
        'events.ProcessEvent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Последнее событие',
    )
    completion_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='Процент выполнения',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата последнего обновления',
    )

    class Meta:
        db_table = 'customer_order'
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order_number} [{self.get_current_stage_code_display()}]'


class OrderLine(models.Model):
    """
    Строка заказа — отдельная товарная позиция в составе заказа.

    Фиксирует, какой товар и в каком количестве требуется по заказу.

    Связи:
        OrderLine M:1 CustomerOrder
        OrderLine M:1 Product
        OrderLine 1:M BatchReservation
    """

    order_line_id = models.BigAutoField(
        primary_key=True,
        verbose_name='ID строки заказа',
    )
    order = models.ForeignKey(
        'orders.CustomerOrder',
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Заказ',
    )
    product = models.ForeignKey(
        'references.Product',
        on_delete=models.PROTECT,
        related_name='order_lines',
        verbose_name='Товар',
    )
    requested_qty = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        verbose_name='Требуемое количество',
    )

    class Meta:
        db_table = 'order_line'
        verbose_name = 'Строка заказа'
        verbose_name_plural = 'Строки заказа'

    def __str__(self):
        return f'{self.order.order_number} / {self.product.sku_code} × {self.requested_qty}'
