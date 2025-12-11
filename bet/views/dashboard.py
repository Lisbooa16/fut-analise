from datetime import date, timedelta

from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from bet.models import Bankroll, Bet
from get_events import SofaScore
from jogos.models import RunningToday


def dashboard(request):
    """Visão geral: banca + métricas reais."""

    today = date.today().isoformat()
    if not RunningToday.objects.filter(data=today, rodou=True).exists():
        try:
            SofaScore(["2025-12-10"]).get_events()
            RunningToday.objects.update_or_create(data=today, defaults={"rodou": True})
        except Exception as exc:
            print(f"Erro ao rodar scraper: {exc}")

    bankroll, _ = Bankroll.objects.get_or_create(name="Banca Principal")

    all_bets = Bet.objects.all()

    metrics = all_bets.aggregate(
        total_stake_green=Sum("stake", filter=Q(result="GREEN")),
        total_return_green=Sum("potential_profit", filter=Q(result="GREEN")),
        total_loss=Sum("stake", filter=Q(result="RED")),
        greens_30d=Count(
            "id",
            filter=Q(
                result="GREEN", created_at__gte=timezone.now() - timedelta(days=30)
            ),
        ),
    )

    stake_green = metrics["total_stake_green"] or 0
    return_green = metrics["total_return_green"] or 0
    total_loss = metrics["total_loss"] or 0

    profit_net = return_green - stake_green
    overall_performance = profit_net - total_loss

    recent_bets = all_bets.order_by("-created_at")[:8]

    return render(
        request,
        "betting/dashboard.html",
        {
            "user_name": request.user.first_name or request.user.username,
            "bankroll": bankroll,
            "bets": recent_bets,
            "chart_profit": profit_net,
            "chart_loss": total_loss,
            "chart_balance": bankroll.balance,
            "greens_last_30": metrics["greens_30d"],
            "users_online": 1,
        },
    )
