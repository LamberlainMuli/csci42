# marketplace/templatetags/marketplace_tags.py
from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs):
    """
    Updates the current query string with new parameter values.
    Preserves existing parameters unless explicitly overridden.
    Usage: {% query_transform request key1=value1 key2=value2 %}
    """
    request = context['request']
    updated = request.GET.copy()
    for k, v in kwargs.items():
        if v is not None:
            updated[k] = v
        else:
            updated.pop(k, 0)  # Remove key if value is None
    return updated.urlencode()

# Remember to load the tag in your template: {% load marketplace_tags %}