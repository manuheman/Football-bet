from django import template

register = template.Library()

@register.filter
def to(start, end):
    """Returns a range from start to end inclusive"""
    return range(start, end+1)

@register.filter
def dict_get(d, key):
    """Returns the value for key in dictionary d, or None if not found"""
    return d.get(key)

@register.filter
def mul(value, arg):
    """Multiplies value by arg"""
    return value * arg