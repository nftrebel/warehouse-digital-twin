from django.contrib import admin
from .models import Product, StorageLocation


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku_code', 'product_name', 'unit_of_measure')
    search_fields = ('sku_code', 'product_name')


@admin.register(StorageLocation)
class StorageLocationAdmin(admin.ModelAdmin):
    list_display = ('location_code', 'location_name', 'location_type')
    list_filter = ('location_type',)
    search_fields = ('location_code', 'location_name')
