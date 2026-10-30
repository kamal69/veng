from decimal import Decimal
from django import template

register = template.Library()


@register.filter(name='inr_format')
def inr_format(value):
    """
    Format a decimal/float number in Indian Rupee format (e.g. ₹ 12,34,567.89).
    """
    if value is None or value == '':
        return '₹ 0.00'
    try:
        val = Decimal(str(value))
    except Exception:
        return f"₹ {value}"

    is_negative = val < 0
    val = abs(val)

    # Format 2 decimal places
    val_str = f"{val:.2f}"
    int_part, dec_part = val_str.split('.')

    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        # Last 3 digits
        last_three = int_part[-3:]
        remaining = int_part[:-3]
        # In Indian system, remaining digits are grouped in pairs of 2 from right to left
        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.insert(0, remaining)
        formatted_int = ",".join(groups) + "," + last_three

    result = f"₹ {formatted_int}.{dec_part}"
    if is_negative:
        result = f"-{result}"
    return result


@register.filter(name='role_badge_class')
def role_badge_class(role):
    mapping = {
        'ADMIN': 'bg-danger',
        'MANAGEMENT': 'bg-primary',
        'SITE_ENGINEER': 'bg-info text-dark',
    }
    return mapping.get(role, 'bg-secondary')


@register.filter(name='status_badge_class')
def status_badge_class(status):
    mapping = {
        'DRAFT': 'bg-secondary',
        'SUBMITTED': 'bg-warning text-dark',
        'APPROVED': 'bg-success',
        'RETURNED': 'bg-danger',
        'ACTIVE': 'bg-success',
        'ON_HOLD': 'bg-warning text-dark',
        'COMPLETED': 'bg-info text-dark',
        'IN_PROGRESS': 'bg-primary',
        'NEAR_COMPLETION': 'bg-info text-dark',
        'MATERIAL_SHORTAGE': 'bg-danger',
        'RAIN_DELAY': 'bg-secondary',
    }
    return mapping.get(status, 'bg-secondary')
