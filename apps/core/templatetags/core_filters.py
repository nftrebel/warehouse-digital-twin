"""
Кастомные шаблонные фильтры.

qty — форматирует Decimal, убирая лишние нули после запятой:
    300.000 → 300
    50.500 → 50.5
    12.750 → 12.75
"""

from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


@register.filter
def qty(value):
    """
    Форматирует количество: убирает лишние нули после точки.
    300.000 → '300'
    50.500 → '50.5'
    """
    if value is None:
        return '—'
    try:
        d = Decimal(str(value))
        # Normalize убирает trailing zeros: 300.000 → 3E+2, поэтому
        # используем свой подход
        result = f'{d:f}'  # '300.000'
        if '.' in result:
            result = result.rstrip('0').rstrip('.')
        return result
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
