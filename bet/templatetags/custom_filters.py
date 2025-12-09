from django import template

register = template.Library()


@register.filter
def replace(value, arg):
    """
    Substitui todas as ocorrências de uma substring (arg[0]) por outra (arg[1])
    A sintaxe esperada no template é: |replace:"antigo|novo"
    """
    if not isinstance(value, str):
        return value

    if isinstance(arg, str):
        try:
                                         
            old, new = arg.split("|")
        except ValueError:
                                                                                
            return value.replace(arg, '')

        return value.replace(old, new)
    return value
