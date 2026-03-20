from django.contrib import admin
from .models import ProcessEvent


@admin.register(ProcessEvent)
class ProcessEventAdmin(admin.ModelAdmin):
    list_display = (
        'event_id', 'event_type_code', 'source_system',
        'event_time', 'processing_status', 'batch', 'order',
    )
    list_filter = ('event_type_code', 'processing_status', 'source_system')
    search_fields = ('external_event_id', 'batch__batch_number', 'order__order_number')
    readonly_fields = ('received_at',)
    date_hierarchy = 'event_time'
