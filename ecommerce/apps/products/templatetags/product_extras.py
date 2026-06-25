from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Usage: {{ my_dict|get_item:some_key }}"""
    return dictionary.get(key, [])


@register.filter
def slice_chunks(value, chunk_size):
    """Split a list into sublists of size chunk_size."""
    value = list(value)
    return [value[i:i + chunk_size] for i in range(0, len(value), chunk_size)]
