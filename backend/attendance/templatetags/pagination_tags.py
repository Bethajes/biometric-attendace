from django import template
from django.http import QueryDict

register = template.Library()


@register.filter
def remove_page_param(query_string):
    """Remove the 'page' parameter from a query string."""
    params = QueryDict(query_string)
    cleaned = params.copy()
    cleaned.pop('page', None)
    encoded = cleaned.urlencode()
    return encoded
