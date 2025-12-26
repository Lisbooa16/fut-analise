# bet/views/pre_bet_market_engine.py
from decimal import Decimal

from django.shortcuts import get_object_or_404, render
from django.views import View

from bet.models import PreBetDecision
from bet.utils.market_engine import calculate_market_prob, classify_confidence
from bet.utils.market_rules import MARKET_TYPE_MAP
from bet.utils.market_suggest import suggest_best_market
from jogos.models import Match


class PreBetMarketEngineView(View):
    template_name = "betting/pre_bet_analysis.html"

    def extract_available_markets(self, match_data, allowed_markets=None):
        """
        Retorna apenas mercados que:
        - existem no streaks_json
        - têm valor X/Y (probabilidade)
        - estão mapeados no sistema (MARKET_TYPE_MAP)
        """

        available = set()

        for section in ("general", "head2head"):
            for item in match_data.get(section, []):
                name = item.get("name")
                value = item.get("value", "")

                # só aceita probabilidades do tipo X/Y
                if "/" not in value:
                    continue

                # se passar lista permitida, valida
                if allowed_markets and name not in allowed_markets:
                    continue

                available.add(name)

        return sorted(available)

    def get(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)

        return render(
            request,
            self.template_name,
            {"match": match, "markets": MARKET_TYPE_MAP.keys()},
        )

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)

        market = request.POST.get("market")
        odd = Decimal(request.POST.get("odd"))

        match_data = match.streaks_json or {}

        model_prob = calculate_market_prob(match_data, market)
        book_prob = float(1 / odd)

        decision = "NÃO APOSTAR"
        confidence = "SEM VALOR"

        if model_prob:
            confidence = classify_confidence(model_prob, book_prob)
            if confidence != "SEM VALOR":
                decision = "APOSTAR"

        if model_prob is not None:
            PreBetDecision.objects.create(
                match=match,
                market=market,
                prob_final=model_prob,
                odd=float(odd),
                book_prob=book_prob,
                decision=(decision == "APOSTAR"),
            )
        odds_by_market = {
            market: odd,
        }

        best_markets = suggest_best_market(match, odds_by_market)
        available_markets = self.extract_available_markets(
            match_data, allowed_markets=MARKET_TYPE_MAP.keys()
        )

        context = {
            "match": match,
            "markets": available_markets,
            "selected_market": market,
            "odd": float(odd),
            "analysis": (
                {
                    "model_prob": round(model_prob * 100, 1) if model_prob else None,
                    "book_prob": round(book_prob * 100, 1),
                    "difference": (
                        round((model_prob - book_prob) * 100, 1) if model_prob else None
                    ),
                    "decision": decision,
                    "confidence": confidence,
                }
                if model_prob
                else None
            ),
            "error": None if model_prob else "Dados insuficientes para este mercado.",
            "best_markets": best_markets[:1],
        }
        return render(request, self.template_name, context)
