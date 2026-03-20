from django.contrib import admin
from .models import Batch, BatchReservation


class BatchReservationInline(admin.TabularInline):
    model = BatchReservation
    extra = 0
    readonly_fields = ('reservation_id',)


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = (
        'batch_number', 'product', 'quantity_total',
        'current_stage_code', 'current_location', 'updated_at',
    )
    list_filter = ('current_stage_code',)
    search_fields = ('batch_number', 'product__sku_code', 'product__product_name')
    readonly_fields = ('updated_at',)
    inlines = [BatchReservationInline]


@admin.register(BatchReservation)
class BatchReservationAdmin(admin.ModelAdmin):
    list_display = (
        'reservation_id', 'batch', 'order_line',
        'reserved_qty', 'picked_qty', 'reservation_status',
    )
    list_filter = ('reservation_status',)
