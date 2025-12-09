from django import template

register = template.Library()


@register.filter
def replace(value, arg):
    """
    Substitui todas as ocorrências de uma substring (arg[0]) por outra (arg[1])
    A sintaxe esperada no template é: |replace:"antigo|novo"
    """
    if isinstance(arg, str):
        try:
            # Tenta dividir "antigo|novo"
            old, new = arg.split("|")
        except ValueError:
            # Se não houver pipe, apenas substitui o argumento completo por nada
            return value.replace(arg, '')

        return value.replace(old, new)
    return value