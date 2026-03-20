"""
Модели справочников: Product, StorageLocation.

Product — номенклатурная единица товара (SKU).
StorageLocation — складская локация (зона приёмки, ячейка хранения, зона отгрузки и т.д.).
"""

from django.db import models


class Product(models.Model):
    """
    Справочник товаров.

    Хранит информацию о товарных позициях: SKU, наименование, единицу измерения.
    Используется как единый источник данных о товаре, на который ссылаются
    партии (Batch) и строки заказа (OrderLine).

    Связи:
        Product 1:M Batch
        Product 1:M OrderLine
    """

    product_id = models.BigAutoField(
        primary_key=True,
        verbose_name='ID товара',
    )
    sku_code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Код SKU',
        help_text='Уникальный внутренний код товарной позиции',
    )
    product_name = models.CharField(
        max_length=255,
        verbose_name='Наименование товара',
    )
    unit_of_measure = models.CharField(
        max_length=20,
        verbose_name='Единица измерения',
        help_text='Например: шт, кг, л, м',
    )

    class Meta:
        db_table = 'product'
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['sku_code']

    def __str__(self):
        return f'{self.sku_code} — {self.product_name}'


class StorageLocation(models.Model):
    """
    Справочник складских локаций.

    Описывает физические или логические места хранения: зону приёмки,
    ячейку хранения, зону комплектации, буферную зону, зону отгрузки.

    Связи:
        StorageLocation 1:M Batch       (текущее местоположение партии)
        StorageLocation 1:M ProcessEvent (локация, связанная с событием)
    """

    LOCATION_TYPE_CHOICES = [
        ('receiving', 'Зона приёмки'),
        ('storage', 'Зона хранения'),
        ('picking', 'Зона комплектации'),
        ('buffer', 'Буферная зона'),
        ('shipping', 'Зона отгрузки'),
    ]

    location_id = models.BigAutoField(
        primary_key=True,
        verbose_name='ID локации',
    )
    location_code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Код локации',
        help_text='Уникальный код складской локации, например: A-01-03',
    )
    location_name = models.CharField(
        max_length=255,
        verbose_name='Название локации',
    )
    location_type = models.CharField(
        max_length=50,
        choices=LOCATION_TYPE_CHOICES,
        verbose_name='Тип локации',
    )

    class Meta:
        db_table = 'storage_location'
        verbose_name = 'Складская локация'
        verbose_name_plural = 'Складские локации'
        ordering = ['location_code']

    def __str__(self):
        return f'{self.location_code} ({self.get_location_type_display()})'
