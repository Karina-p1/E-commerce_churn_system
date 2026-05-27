from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Usage: {{ my_dict|get_item:some_key }}"""
    return dictionary.get(key, [])
