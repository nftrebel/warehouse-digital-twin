"""
Views веб-интерфейса цифрового двойника.

Экраны: дашборд, цифровой двойник, партии, заказы, события, локации, аналитика.
"""

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum, F
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from apps.references.models import Product, StorageLocation
from apps.inventory.models import Batch, BatchReservation
from apps.orders.models import CustomerOrder, OrderLine
from apps.events.models import ProcessEvent
from apps.events.services import EventProcessor


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    active_batches = Batch.objects.exclude(current_stage_code='shipped').count()
    active_orders = CustomerOrder.objects.exclude(current_stage_code__in=['shipped', 'closed', 'cancelled']).count()
    events_today = ProcessEvent.objects.filter(received_at__gte=today_start).count()
    overdue_orders = CustomerOrder.objects.filter(
        planned_ship_date__lt=now,
    ).exclude(current_stage_code__in=['shipped', 'closed', 'cancelled']).count()

    # Batch stages distribution
    batch_stages_qs = (
        Batch.objects.values('current_stage_code')
        .annotate(count=Count('batch_id'))
        .order_by('current_stage_code')
    )
    total_batches = Batch.objects.count() or 1
    batch_stages = [
        {**s, 'percent': round(s['count'] / total_batches * 100)}
        for s in batch_stages_qs
    ]

    # Order stages distribution
    order_stages_qs = (
        CustomerOrder.objects.values('current_stage_code')
        .annotate(count=Count('order_id'))
        .order_by('current_stage_code')
    )
    total_orders = CustomerOrder.objects.count() or 1
    order_stages = [
        {**s, 'percent': round(s['count'] / total_orders * 100)}
        for s in order_stages_qs
    ]

    recent_events = (
        ProcessEvent.objects
        .select_related('batch', 'order')
        .order_by('-event_time')[:10]
    )

    return render(request, 'ui/dashboard.html', {
        'active_page': 'dashboard',
        'active_batches': active_batches,
        'active_orders': active_orders,
        'events_today': events_today,
        'overdue_orders': overdue_orders,
        'batch_stages': batch_stages,
        'order_stages': order_stages,
        'recent_events': recent_events,
    })


# ---------------------------------------------------------------------------
# Digital Twin
# ---------------------------------------------------------------------------

@login_required
def digital_twin(request):
    BATCH_STAGES = [
        ('expected', 'Ожидает'),
        ('received', 'Принята'),
        ('placed', 'Размещена'),
        ('stored', 'Хранение'),
        ('reserved', 'Резерв'),
        ('shipped', 'Отгружена'),
    ]

    batch_counts = dict(
        Batch.objects.values_list('current_stage_code')
        .annotate(c=Count('batch_id'))
        .values_list('current_stage_code', 'c')
    )
    batch_pipeline = [
        {'code': code, 'label': label, 'count': batch_counts.get(code, 0)}
        for code, label in BATCH_STAGES
    ]

    batches = (
        Batch.objects
        .select_related('product', 'current_location')
        .exclude(current_stage_code='shipped')
        .order_by('-updated_at')[:50]
    )
    orders = (
        CustomerOrder.objects
        .exclude(current_stage_code__in=['closed', 'cancelled'])
        .order_by('-updated_at')[:50]
    )
    locations = (
        StorageLocation.objects
        .annotate(batch_count=Count('batches'))
        .order_by('location_code')
    )

    return render(request, 'ui/digital_twin.html', {
        'active_page': 'digital-twin',
        'batch_pipeline': batch_pipeline,
        'batches': batches,
        'orders': orders,
        'locations': locations,
    })


# ---------------------------------------------------------------------------
# Batches
# ---------------------------------------------------------------------------

@login_required
def batch_list(request):
    qs = Batch.objects.select_related('product', 'current_location')

    search = request.GET.get('search', '').strip()
    stage_filter = request.GET.get('stage', '').strip()
    quick_filter = request.GET.get('filter', '').strip()

    # Быстрый фильтр с дашборда
    if quick_filter == 'active':
        qs = qs.exclude(current_stage_code='shipped')

    if search:
        qs = qs.filter(
            Q(batch_number__icontains=search) |
            Q(product__sku_code__icontains=search) |
            Q(product__product_name__icontains=search)
        )
    if stage_filter:
        qs = qs.filter(current_stage_code=stage_filter)

    return render(request, 'ui/batch_list.html', {
        'active_page': 'batches',
        'batches': qs.order_by('-updated_at'),
        'search': search,
        'stage_filter': stage_filter,
        'quick_filter': quick_filter,
        'stage_choices': Batch.STAGE_CHOICES,
    })


@login_required
def batch_detail(request, batch_id):
    batch = get_object_or_404(
        Batch.objects.select_related('product', 'current_location'),
        batch_id=batch_id,
    )
    events = (
        ProcessEvent.objects
        .filter(batch=batch)
        .order_by('-event_time')
    )
    reservations = (
        BatchReservation.objects
        .filter(batch=batch)
        .select_related('order_line__order', 'order_line__product')
    )

    return render(request, 'ui/batch_detail.html', {
        'active_page': 'batches',
        'batch': batch,
        'events': events,
        'reservations': reservations,
    })


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@login_required
def order_list(request):
    qs = CustomerOrder.objects.all()

    search = request.GET.get('search', '').strip()
    stage_filter = request.GET.get('stage', '').strip()
    priority_filter = request.GET.get('priority', '').strip()
    quick_filter = request.GET.get('filter', '').strip()

    # Быстрые фильтры с дашборда
    if quick_filter == 'active':
        qs = qs.exclude(current_stage_code__in=['shipped', 'closed', 'cancelled'])
    elif quick_filter == 'overdue':
        qs = qs.filter(
            planned_ship_date__lt=timezone.now(),
        ).exclude(current_stage_code__in=['shipped', 'closed', 'cancelled'])

    if search:
        qs = qs.filter(order_number__icontains=search)
    if stage_filter:
        qs = qs.filter(current_stage_code=stage_filter)
    if priority_filter:
        qs = qs.filter(priority_code=priority_filter)

    return render(request, 'ui/order_list.html', {
        'active_page': 'orders',
        'orders': qs.order_by('-created_at'),
        'search': search,
        'stage_filter': stage_filter,
        'priority_filter': priority_filter,
        'quick_filter': quick_filter,
        'stage_choices': CustomerOrder.STAGE_CHOICES,
        'priority_choices': CustomerOrder.PRIORITY_CHOICES,
    })


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(CustomerOrder, order_id=order_id)

    lines = order.lines.select_related('product').all()
    # Add total_reserved for each line
    lines_data = []
    for line in lines:
        total_reserved = line.reservations.aggregate(
            total=Sum('reserved_qty')
        )['total'] or 0
        line.total_reserved = total_reserved
        lines_data.append(line)

    events = (
        ProcessEvent.objects
        .filter(order=order)
        .order_by('-event_time')
    )
    reservations = (
        BatchReservation.objects
        .filter(order_line__order=order)
        .select_related('batch__product', 'order_line')
    )

    return render(request, 'ui/order_detail.html', {
        'active_page': 'orders',
        'order': order,
        'lines': lines_data,
        'events': events,
        'reservations': reservations,
    })


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@login_required
def event_list(request):
    qs = ProcessEvent.objects.select_related('batch', 'order', 'location')

    type_filter = request.GET.get('event_type', '').strip()
    status_filter = request.GET.get('status', '').strip()
    search = request.GET.get('search', '').strip()

    if type_filter:
        qs = qs.filter(event_type_code=type_filter)
    if status_filter:
        qs = qs.filter(processing_status=status_filter)
    if search:
        qs = qs.filter(
            Q(batch__batch_number__icontains=search) |
            Q(order__order_number__icontains=search) |
            Q(external_event_id__icontains=search)
        )

    return render(request, 'ui/event_list.html', {
        'active_page': 'events',
        'events': qs.order_by('-event_time')[:200],
        'type_filter': type_filter,
        'status_filter': status_filter,
        'search': search,
        'type_choices': ProcessEvent.EVENT_TYPE_CHOICES,
        'status_choices': ProcessEvent.PROCESSING_STATUS_CHOICES,
    })


@login_required
def event_detail(request, event_id):
    event = get_object_or_404(
        ProcessEvent.objects.select_related('batch', 'order', 'location'),
        event_id=event_id,
    )
    payload_pretty = json.dumps(
        event.payload_json, ensure_ascii=False, indent=2
    ) if event.payload_json else ''

    return render(request, 'ui/event_detail.html', {
        'active_page': 'events',
        'event': event,
        'payload_pretty': payload_pretty,
    })


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

@login_required
def location_list(request):
    locations = (
        StorageLocation.objects
        .annotate(batch_count=Count('batches'))
        .order_by('location_type', 'location_code')
    )
    return render(request, 'ui/location_list.html', {
        'active_page': 'locations',
        'locations': locations,
    })


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@login_required
def analytics(request):
    total_events = ProcessEvent.objects.count() or 1

    # Events by type
    events_by_type = list(
        ProcessEvent.objects
        .values('event_type_code')
        .annotate(count=Count('event_id'))
        .order_by('-count')
    )
    for item in events_by_type:
        item['percent'] = round(item['count'] / total_events * 100)

    # Events by source
    events_by_source = list(
        ProcessEvent.objects
        .values('source_system')
        .annotate(count=Count('event_id'))
        .order_by('-count')
    )
    for item in events_by_source:
        item['percent'] = round(item['count'] / total_events * 100)

    # Stage durations (simple approach: difference between consecutive events for same batch)
    stage_durations = _calc_stage_durations()

    total_shipped_orders = CustomerOrder.objects.filter(
        current_stage_code__in=['shipped', 'closed']
    ).count()
    rejected_events = ProcessEvent.objects.filter(processing_status='rejected').count()

    # Simple avg times
    avg_receive_to_place = _calc_avg_transition('batch.received', 'batch.placed')
    avg_pick_to_ship = _calc_avg_transition('order.picking_started', 'shipment.dispatched')

    return render(request, 'ui/analytics.html', {
        'active_page': 'analytics',
        'events_by_type': events_by_type,
        'events_by_source': events_by_source,
        'stage_durations': stage_durations,
        'total_shipped_orders': total_shipped_orders,
        'rejected_events': rejected_events,
        'avg_receive_to_place': avg_receive_to_place,
        'avg_pick_to_ship': avg_pick_to_ship,
    })


def _calc_avg_transition(from_type, to_type):
    """Calculate average time between two event types for the same batch/order."""
    from_events = ProcessEvent.objects.filter(
        event_type_code=from_type, processing_status='applied'
    ).values('batch_id', 'order_id', 'event_time')

    to_events = ProcessEvent.objects.filter(
        event_type_code=to_type, processing_status='applied'
    ).values('batch_id', 'order_id', 'event_time')

    durations = []
    from_map = {}
    for e in from_events:
        key = e['batch_id'] or e['order_id']
        if key:
            from_map[key] = e['event_time']

    for e in to_events:
        key = e['batch_id'] or e['order_id']
        if key and key in from_map:
            delta = e['event_time'] - from_map[key]
            if delta.total_seconds() > 0:
                durations.append(delta)

    if not durations:
        return None

    avg = sum(d.total_seconds() for d in durations) / len(durations)
    return _format_duration(avg)


def _calc_stage_durations():
    """Calculate average durations between stage transitions."""
    transitions = [
        ('received', 'placed'),
        ('placed', 'stored'),
        ('stored', 'reserved'),
        ('reserved', 'shipped'),
    ]
    results = []
    for from_stage, to_stage in transitions:
        from_events = dict(
            ProcessEvent.objects
            .filter(new_stage_code=from_stage, processing_status='applied')
            .values_list('batch_id', 'event_time')
        )
        to_events = dict(
            ProcessEvent.objects
            .filter(new_stage_code=to_stage, processing_status='applied')
            .values_list('batch_id', 'event_time')
        )

        durations = []
        for batch_id, from_time in from_events.items():
            if batch_id and batch_id in to_events:
                delta = (to_events[batch_id] - from_time).total_seconds()
                if delta > 0:
                    durations.append(delta)

        if durations:
            avg = sum(durations) / len(durations)
            results.append({
                'from_stage': from_stage,
                'to_stage': to_stage,
                'avg_duration': _format_duration(avg),
                'count': len(durations),
            })
    return results


def _format_duration(seconds):
    """Format seconds into human readable string."""
    if seconds < 60:
        return f'{int(seconds)} сек'
    elif seconds < 3600:
        return f'{int(seconds // 60)} мин'
    elif seconds < 86400:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f'{hours} ч {minutes} мин'
    else:
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        return f'{days} дн {hours} ч'


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

@login_required
def simulator(request):
    result = None
    result_json = ''

    if request.method == 'POST':
        processor = EventProcessor()
        now = timezone.now()

        # Быстрые сценарии
        scenario = request.POST.get('quick_scenario')
        if scenario:
            result = _run_quick_scenario(scenario, processor, now)
        else:
            # Ручная отправка события
            event_type = request.POST.get('event_type', '')
            source = request.POST.get('source', 'simulator')
            payload_raw = request.POST.get('payload', '{}')

            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                result = {'status': 'error', 'message': 'Некорректный JSON в payload'}
            else:
                object_type = 'batch'
                if event_type.startswith('order.') or event_type.startswith('shipment.'):
                    object_type = 'order'
                elif event_type.startswith('location.'):
                    object_type = 'location'

                object_id = (payload.get('batch_code')
                             or payload.get('order_number')
                             or payload.get('location_code')
                             or 'unknown')

                result = processor.process_event({
                    'event_id': f'sim-{uuid.uuid4().hex[:12]}',
                    'event_type': event_type,
                    'occurred_at': now,
                    'source_system': source,
                    'warehouse_code': 'WH-01',
                    'object_type': object_type,
                    'object_id': object_id,
                    'payload': payload,
                })

        result_json = json.dumps(result, ensure_ascii=False, indent=2, default=str)

    stats = {
        'batches': Batch.objects.count(),
        'orders': CustomerOrder.objects.count(),
        'events': ProcessEvent.objects.count(),
        'locations': StorageLocation.objects.count(),
    }

    return render(request, 'ui/simulator.html', {
        'active_page': 'simulator',
        'result': result,
        'result_json': result_json,
        'stats': stats,
    })


def _run_quick_scenario(scenario, processor, now):
    """Выполняет быстрый сценарий и возвращает результат."""

    if scenario == 'new_batch':
        num = Batch.objects.count() + 1
        batch_code = f'BATCH-SIM-{num:03d}'
        return processor.process_event({
            'event_id': f'sim-{uuid.uuid4().hex[:12]}',
            'event_type': 'batch.received',
            'occurred_at': now,
            'source_system': 'simulator',
            'warehouse_code': 'WH-01',
            'object_type': 'batch',
            'object_id': batch_code,
            'payload': {
                'batch_code': batch_code,
                'product_sku': 'SKU-1001',
                'qty': 50,
                'supplier_doc': f'SUP-SIM-{num:03d}',
                'receiving_gate': 'RECV-01',
            },
        })

    elif scenario == 'place_batch':
        batch = Batch.objects.filter(current_stage_code='received').order_by('-updated_at').first()
        if not batch:
            return {'status': 'error', 'message': 'Нет партий в статусе received'}
        return processor.process_event({
            'event_id': f'sim-{uuid.uuid4().hex[:12]}',
            'event_type': 'batch.placed',
            'occurred_at': now,
            'source_system': 'simulator',
            'warehouse_code': 'WH-01',
            'object_type': 'batch',
            'object_id': batch.batch_number,
            'payload': {
                'batch_code': batch.batch_number,
                'qty': float(batch.quantity_total),
                'to_location': 'A-01-01',
            },
        })

    elif scenario == 'new_order':
        num = CustomerOrder.objects.count() + 1
        order_code = f'ORD-SIM-{num:03d}'
        return processor.process_event({
            'event_id': f'sim-{uuid.uuid4().hex[:12]}',
            'event_type': 'order.created',
            'occurred_at': now,
            'source_system': 'simulator',
            'warehouse_code': 'WH-01',
            'object_type': 'order',
            'object_id': order_code,
            'payload': {
                'order_number': order_code,
                'priority': 'normal',
                'planned_ship_at': (now + timedelta(days=2)).isoformat(),
                'items': [{'product_sku': 'SKU-1001', 'qty_requested': 10}],
            },
        })

    elif scenario == 'block_location':
        return processor.process_event({
            'event_id': f'sim-{uuid.uuid4().hex[:12]}',
            'event_type': 'location.blocked',
            'occurred_at': now,
            'source_system': 'simulator',
            'warehouse_code': 'WH-01',
            'object_type': 'location',
            'object_id': 'PICK-02',
            'payload': {
                'location_code': 'PICK-02',
                'reason': 'Техническое обслуживание (симуляция)',
            },
        })

    return {'status': 'error', 'message': f'Неизвестный сценарий: {scenario}'}
