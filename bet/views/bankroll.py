from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from bet.models import Bankroll, Bet


def _parse_decimal(value: str | None) -> Decimal:
    if value is None:
        raise ValueError("Nenhum valor informado.")
    return Decimal(value.replace(",", "."))


def _bankroll_totals(bets):
    return (
        bets.filter(result="GREEN").aggregate(Sum("potential_profit"))[
            "potential_profit__sum"
        ]
        or Decimal("0")
    ), (bets.filter(result="RED").aggregate(Sum("stake"))["stake__sum"] or Decimal("0"))


def bankroll_view(request):
    """Exibe a banca e permite adicionar saldo."""

    bankroll, _ = Bankroll.objects.get_or_create(
        name="Banca Principal", defaults={"balance": 0}
    )

    if request.method == "POST":
        action = request.POST.get("action")
        amount = request.POST.get("amount")

        try:
            value = _parse_decimal(amount)

            if value <= 0:
                messages.error(request, "O valor deve ser maior que zero.")
            elif action in {"increase", "increese"}:
                bankroll.deposit(value, note="Depósito manual")
                messages.success(request, f"💰 Adicionado R$ {value} à banca!")
                return redirect("bankroll_view")
            elif action == "remove":
                bankroll.withdraw(value, note="Saque manual")
                messages.success(request, f"💸 Removido R$ {value} da banca!")
                return redirect("bankroll_view")
            else:
                messages.error(request, "Ação inválida.")

        except (InvalidOperation, ValueError) as exc:
            messages.error(request, f"Valor inválido. {exc}")
        except Exception as exc:
            messages.error(request, f"Erro ao processar: {exc}")

    bets = bankroll.bets.all().order_by("-created_at")
    total_green, total_red = _bankroll_totals(bets)

    return render(
        request,
        "betting/bankroll.html",
        {
            "bankroll": bankroll,
            "bets": bets,
            "total_green": total_green,
            "total_red": total_red,
        },
    )


def update_bet_result(request, bet_id):
    """Atualiza o resultado da aposta (Green ou Red)."""
    bet = get_object_or_404(Bet, id=bet_id)

    result = request.GET.get("result")
    if result == "green":
        bet.settle_bet(is_green=True)
        messages.success(
            request, "Aposta marcada como GREEN! Lucro adicionado à banca."
        )
    elif result == "red":
        bet.settle_bet(is_green=False)
        messages.warning(request, "Aposta marcada como RED. Nenhum valor retornado.")
    else:
        messages.error(request, "Resultado inválido.")

    return redirect("bankroll_view")
