from django.contrib import admin
from .models import CustomerOrder, OrderLine


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    readonly_fields = ('order_line_id',)


@admin.register(CustomerOrder)
class CustomerOrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number', 'priority_code', 'current_stage_code',
        'completion_percent', 'planned_ship_date', 'created_at',
    )
    list_filter = ('current_stage_code', 'priority_code')
    search_fields = ('order_number',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [OrderLineInline]


@admin.register(OrderLine)
class OrderLineAdmin(admin.ModelAdmin):
    list_display = ('order_line_id', 'order', 'product', 'requested_qty')
    search_fields = ('order__order_number', 'product__sku_code')
