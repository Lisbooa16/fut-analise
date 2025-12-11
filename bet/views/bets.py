from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from bet.models import Bankroll, Bet, PossibleBet
from bet.utils import generate_bankroll_alerts
from jogos.models import Match


def create_bet_from_model(request, pb_id):
    pb = get_object_or_404(PossibleBet, id=pb_id)
    bankroll = Bankroll.objects.first()

    try:
        match = Match.objects.get(external_id=pb.event_id)
    except Match.DoesNotExist:
        messages.error(request, "Não foi possível encontrar o jogo desta aposta.")
        return redirect("dashboard")

    stake = Decimal("10.00")
    odd = Decimal("1.50")

    bet = Bet.objects.create(
        bankroll=bankroll,
        match=match,
        market=pb.market,
        odd=odd,
        stake=stake,
        potential_profit=stake * odd,
    )

    bankroll.withdraw(stake, note=f"Aposta gerada a partir do modelo: {pb.market}")
    bankroll.save(update_fields=["balance"])

    messages.success(request, f"Aposta criada: {pb.market}")
    return redirect("match_detail", pk=match.id)


def get_recommended_stake_and_odd(bankroll, probability=None):
    """
    Retorna (stake_recomendada, odd_recomendada)
    probability = probabilidade em % (ex: 67.7)
    """

    if probability is None:
        percent = Decimal("0.01")
    elif probability >= 70:
        percent = Decimal("0.02")
    elif probability >= 55:
        percent = Decimal("0.015")
    else:
        percent = Decimal("0.01")

    stake = bankroll.balance * percent

    if probability:
        prob_decimal = Decimal(probability) / Decimal("100")
        odd_fair = Decimal("1") / prob_decimal
        odd_recommended = odd_fair.quantize(Decimal("0.01"))
    else:
        odd_recommended = Decimal("1.50")

    return (stake.quantize(Decimal("0.01")), odd_recommended)


def place_bet(request, match_id):
    match = get_object_or_404(Match, id=match_id)
    bankroll, _ = Bankroll.objects.get_or_create(name="Banca Principal")
    alerts = generate_bankroll_alerts(bankroll)

    pre_market = request.GET.get("market")
    pre_odd = request.GET.get("odd")

    probability = None
    if hasattr(match, "analysis"):
        try:
            probs = getattr(match.analysis, "probabilities", {})
            probability = probs.get("over_2_5")
        except Exception:
            pass

    recommended_stake, recommended_odd = get_recommended_stake_and_odd(
        bankroll, probability
    )

    if pre_odd:
        recommended_odd = pre_odd

    if request.method == "POST":
        market = request.POST.get("market")
        raw_odd = request.POST.get("odd")
        raw_stake = request.POST.get("stake")

        try:
            odd = Decimal(raw_odd.replace(",", "."))
            stake = Decimal(raw_stake.replace(",", "."))

            if stake <= 0 or odd <= 1:
                messages.error(request, "Stake deve ser positiva e Odd maior que 1.")
            elif bankroll.balance < stake:
                messages.error(
                    request, f"Saldo insuficiente. Você tem R$ {bankroll.balance}."
                )
            else:
                bet = Bet.objects.create(
                    bankroll=bankroll,
                    match=match,
                    market=market,
                    odd=odd,
                    stake=stake,
                )

                bet.register_bet()

                messages.success(
                    request,
                    f"⚽ Aposta confirmada em {match.home_team} vs {match.away_team}!",
                )
                return redirect("dashboard")

        except Exception as exc:
            messages.error(request, f"Erro: {exc}")

    return render(
        request,
        "betting/place_bet.html",
        {
            "match": match,
            "bankroll": bankroll,
            "recommended_stake": recommended_stake,
            "recommended_odd": recommended_odd,
            "probability": probability,
            "alerts": alerts,
            "pre_market": pre_market,
            "pre_odd": pre_odd,
        },
    )
