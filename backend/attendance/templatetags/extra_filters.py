from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.filter
@stringfilter
def replace(value, arg):
    """Replace all occurrences of a substring, e.g. {{ value|replace:"_| " }}."""
    old, sep, new = arg.partition('|')
    if not sep:
        return value
    return value.replace(old, new)


@register.filter
def div(value, arg):
    """Safe division, e.g. {{ worked|div:expected }}."""
    try:
        divisor = float(arg)
        dividend = float(value)
    except (TypeError, ValueError):
        return 0
    if divisor == 0:
        return 0
    return dividend / divisor
