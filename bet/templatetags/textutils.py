from django import template

register = template.Library()

ERROR_PATTERNS = [
    "invalid session id",
    "erro na análise",
    "stacktrace",
    "selenium",
    "timed out",
    "connection refused",
]


@register.filter
def hide_analysis_errors(text: str) -> str:
    if not text:
        return ""
    lower = str(text).strip().lower()
    if any(p in lower for p in ERROR_PATTERNS):
        return ""
    return text
