from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter
def currency_brl(value):
    """Formata número como moeda brasileira (R$ 1.234,56)."""

    if value is None:
        return "R$ 0,00"

    try:
        numeric = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return "R$ 0,00"

    return f"R$ {numeric:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter
def subtract(a, b):
    try:
        return float(a) - float(b)
    except (TypeError, ValueError):
        return 0


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
    """Oculta mensagens de erro conhecidas presentes em blocos de texto."""

    if not text:
        return ""

    lower = str(text).strip().lower()
    if any(pattern in lower for pattern in ERROR_PATTERNS):
        return ""
    return text


@register.filter
def replace(value, arg):
    """Substitui todas as ocorrências de uma substring (arg[0]) por outra (arg[1])."""

    if not isinstance(value, str):
        return value

    if isinstance(arg, str):
        try:
            old, new = arg.split("|")
        except ValueError:
            return value.replace(arg, "")

        return value.replace(old, new)
    return value


@register.filter
def get_stat_value(data_object, key_name):
    """Retorna o valor de um atributo ou chave de dicionário de um objeto."""

    if data_object is None:
        return 0

    if hasattr(data_object, key_name):
        return getattr(data_object, key_name)

    if isinstance(data_object, dict):
        return data_object.get(key_name, 0)

    return 0


@register.filter
def stat_key_suffix(prefix, team_suffix):
    """Constrói uma chave de estatística: 'possession'|stat_key_suffix:'home' -> 'possession_home'."""

    return f"{prefix}_{team_suffix}"


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)
