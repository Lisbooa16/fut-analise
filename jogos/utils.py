import json
from datetime import datetime

from django.db import transaction
from django.utils.timezone import now

from jogos.models import League, Match, MatchStats, Season, Team


def save_sofascore_data(
    event,
    stats,
    insights,
    streaks,
    standings,
    previsao,
    raw_event_json,
    raw_statistics_json,
):
    """
    Salva League, Season, Team, Match e MatchStats
    usando os dados já processados do Sofascore.

    OBS: aqui `stats` é o bloco `result["stats"]`:
    {
        "xg": {"home": ..., "away": ...},
        "shots": {"home": ..., "away": ...},
        "shots_on": {"home": ..., "away": ...},
        "posse": {"home": ..., "away": ...}
    }
    """

    # -------------------------
    # LEAGUE
    # -------------------------
    league_name = event["tournament"]["name"]
    league_country = event["tournament"]["category"]["name"]

    league_obj, _ = League.objects.get_or_create(
        name=league_name,
        defaults={"country": league_country},
    )

    # -------------------------
    # SEASON
    # -------------------------
    season_name = event["season"]["name"]

    season_obj, _ = Season.objects.get_or_create(
        name=season_name,
        league=league_obj,
    )

    # -------------------------
    # TEAMS
    # -------------------------
    home_team, _ = Team.objects.get_or_create(
        name=event["homeTeam"]["name"],
        defaults={"league": league_obj},
    )

    away_team, _ = Team.objects.get_or_create(
        name=event["awayTeam"]["name"],
        defaults={"league": league_obj},
    )

    # -------------------------
    # MATCH
    # -------------------------
    score_home = event.get("homeScore", {}).get("current")
    score_away = event.get("awayScore", {}).get("current")

    ts = event.get("startTimestamp")
    date_obj = datetime.fromtimestamp(ts) if ts else None

    match_obj, created = Match.objects.update_or_create(
        external_id=event["id"],
        defaults={
            "season": season_obj,
            "home_team": home_team,
            "away_team": away_team,
            "date": date_obj,
            "home_team_score": score_home,
            "away_team_score": score_away,
            "raw_event_json": raw_event_json,
            "raw_statistics_json": raw_statistics_json,
            "finalizado": event["status"]["type"] == "finished",
        },
    )

    # Atualização mínima
    if score_home is not None:
        match_obj.home_team_score = score_home

    if score_away is not None:
        match_obj.away_team_score = score_away

    match_obj.finalizado = event["status"]["type"] == "finished"

    # -------------------------
    # MONTAR SUMMARY
    # -------------------------
    summary = (
        f"{home_team.name} {score_home} x {score_away} {away_team.name}\n\n"
        "📌 INSIGHTS\n"
        + "\n".join(f"- {i}" for i in insights)
        + "\n\n📌 PREVISÃO AUTOMÁTICA\n"
        + json.dumps(previsao, indent=2, ensure_ascii=False)
        + "\n\n📌 STREAKS\n"
        + json.dumps(streaks, indent=2, ensure_ascii=False)
        + "\n\n📌 STANDINGS\n"
        + json.dumps(standings, indent=2, ensure_ascii=False)
    )

    match_obj.analysis = summary
    match_obj.save()

    # -------------------------
    # MATCHSTATS (estatísticas simples)
    # aqui `stats` JÁ É o bloco interno
    # -------------------------
    stats_block = stats or {}

    xg_home = stats_block.get("xg", {}).get("home", 0.0)
    xg_away = stats_block.get("xg", {}).get("away", 0.0)

    shots_home = stats_block.get("shots", {}).get("home", 0.0)
    shots_away = stats_block.get("shots", {}).get("away", 0.0)

    shots_on_home = stats_block.get("shots_on", {}).get("home", 0.0)
    shots_on_away = stats_block.get("shots_on", {}).get("away", 0.0)

    possession_home = stats_block.get("posse", {}).get("home", 0.0)
    possession_away = stats_block.get("posse", {}).get("away", 0.0)

    with transaction.atomic():
        MatchStats.objects.update_or_create(
            match=match_obj,
            defaults=dict(
                team_home=home_team,
                team_away=away_team,
                xg_home=xg_home,
                xg_away=xg_away,
                shots_home=shots_home,
                shots_away=shots_away,
                shots_on_home=shots_on_home,
                shots_on_away=shots_on_away,
                possession_home=possession_home,
                possession_away=possession_away,
                score_home=score_home,
                score_away=score_away,
                summary=summary,
                analyzed_at=now(),
            ),
        )

    return match_obj.id


# utils/stats_predictor.py

import math


def safe(val):
    if val is None:
        return 0
    try:
        return float(val)
    except:
        return 0


def analyze_match(data_event, data_stats):
    """
    Modelo avançado:
    - Suporta pré-live (sem estatísticas)
    - Suporta live (xG, finalizações etc.)
    - Usa força das equipes (userCount)
    - Usa peso da liga
    - Usa vantagem de mandante
    - Gera prob. pré-jogo realistas
    """
    # ============================
    # 1. Info do evento
    # ============================
    home = data_event["homeTeam"]["name"]
    away = data_event["awayTeam"]["name"]

    hc = data_event["homeTeam"].get("userCount", 30000)
    ac = data_event["awayTeam"].get("userCount", 30000)

    league = data_event["tournament"]["name"].lower()
    league_slug = data_event["tournament"]["slug"]

    # pesos reais por liga
    liga_peso = {
        "premier-league": 1.20,
        "la-liga": 1.15,
        "serie-a": 1.10,
        "bundesliga": 1.15,
        "ligue-1": 1.05,
        "brasileirao-serie-a": 1.08,
        "default": 1.00,
    }
    peso_liga = liga_peso.get(league_slug, liga_peso["default"])

    # vantagem do mandante
    mandante_bonus = 1.05

    # ============================
    # 2. Caso PRÉ-LIVE
    # ============================
    if not data_stats or "statistics" not in data_stats:
        # força relativa
        total_force = hc + ac
        home_strength = (hc / total_force) * mandante_bonus
        away_strength = ac / total_force

        # gols esperados baseados na liga
        avg_goals = 2.6 * peso_liga

        # Modelo super simplificado
        lam_home = avg_goals * home_strength * 0.55
        lam_away = avg_goals * away_strength * 0.45

        # probabilidades pré-live
        p_over_2_5 = min(0.88, (lam_home + lam_away) / 2.3)
        p_over_1_5 = min(1, p_over_2_5 + 0.20)
        p_btts = min(1, (lam_home * lam_away) / 1.3)
        p_under_2_5 = 1 - p_over_2_5
        p_goal_h2 = 0.55  # média mundial pré-live

        # favorito
        fav = home if home_strength > away_strength else away

        insights = [
            (
                f"⚽ Liga: {data_event['tournament']['name']}. Expectativa média de gols elevada."
                if peso_liga > 1
                else f"⚽ Liga com tendência mais defensiva ({data_event['tournament']['name']})."
            ),
            f"📌 {home} tem vantagem natural por jogar em casa.",
            f"📊 Força relativa: {home} ({hc}) vs {away} ({ac}).",
            f"⭐ Favorito pré-jogo: {fav}.",
        ]

        return {
            "probabilities": {
                "over_1_5": round(p_over_1_5 * 100, 1),
                "over_2_5": round(p_over_2_5 * 100, 1),
                "under_2_5": round(p_under_2_5 * 100, 1),
                "btts": round(p_btts * 100, 1),
                "goal_h2": round(p_goal_h2 * 100, 1),
            },
            "odds": {
                "over_1_5": round(1 / max(p_over_1_5, 0.01), 2),
                "over_2_5": round(1 / max(p_over_2_5, 0.01), 2),
                "btts": round(1 / max(p_btts, 0.01), 2),
                "goal_h2": round(1 / max(p_goal_h2, 0.01), 2),
                "under_2_5": round(1 / max(p_under_2_5, 0.01), 2),
            },
            "projected_score": f"{lam_home:.1f} x {lam_away:.1f}",
            "recommendation": (
                "Over 1.5 (pré-jogo)"
                if p_over_1_5 > 0.72
                else (
                    "BTTS (pré-jogo)"
                    if p_btts > 0.65
                    else "Nenhuma entrada segura pré-live"
                )
            ),
            "confidence": round((p_over_2_5 * 0.6 + p_btts * 0.4) * 100, 1),
            "insights": insights,
        }

    # ============================
    # 3. LIVE — usa seu modelo atual
    # ============================

    # bloco ALL
    stats_list = data_stats["statistics"]
    all_stats = next((b for b in stats_list if b.get("period") == "ALL"), None)
    if not all_stats:
        return analyze_match(data_event, {})  # pré-live

    groups = all_stats.get("groups", [])

    def take(key):
        """extrai estatísticas com segurança"""
        for g in groups:
            for item in g["statisticsItems"]:
                if item.get("key") == key:
                    return safe(item.get("homeValue")), safe(item.get("awayValue"))
        return (0, 0)

    # coleta avançada
    xg_home, xg_away = take("expectedGoals")
    shots_home, shots_away = take("totalShotsOnGoal")
    sot_home, sot_away = take("shotsOnGoal")
    big_home, big_away = take("bigChanceCreated")

    total_xg = xg_home + xg_away
    total_big = big_home + big_away
    total_sot = sot_home + sot_away

    # segundo tempo
    second_half = next((b for b in stats_list if b.get("period") == "2ND"), None)
    xg_h2_home = xg_h2_away = 0
    if second_half:
        for g in second_half.get("groups", []):
            for item in g["statisticsItems"]:
                if item.get("key") == "expectedGoals":
                    xg_h2_home += safe(item.get("homeValue"))
                    xg_h2_away += safe(item.get("awayValue"))

    # modelo poisson
    def poisson(lam, k):
        return (lam**k * math.exp(-lam)) / math.factorial(k)

    p_over_2_5 = 1 - sum(poisson(total_xg, i) for i in range(3))
    p_over_1_5 = min(1, p_over_2_5 + 0.20)
    p_btts = min(1, (xg_home / 1.1) * (xg_away / 1.1))
    p_under_2_5 = 1 - p_over_2_5
    p_goal_h2 = min(1, (xg_h2_home + xg_h2_away) / 0.55)

    projected_home = round(xg_home * 0.9 + sot_home * 0.12, 2)
    projected_away = round(xg_away * 0.9 + sot_away * 0.12, 2)

    # recomendação
    rec = (
        "Over 1.5 gols (LIVE)"
        if p_over_1_5 > 0.72
        else (
            "Ambas Marcam (LIVE)"
            if p_btts > 0.60
            else (
                "Gol no 2º tempo"
                if p_goal_h2 > 0.65
                else "Nenhuma entrada segura ainda"
            )
        )
    )

    # confiança
    confidence = round(min(100, total_xg * 22 + total_big * 10 + total_sot * 3), 1)

    # insights profissionais
    insights = []
    if total_big >= 4:
        insights.append("⚽ Muitas chances claras — jogo muito aberto.")
    if total_sot >= 8:
        insights.append(
            "🔥 Alto volume de finalizações no alvo — forte tendência de gol."
        )
    if xg_home > xg_away:
        insights.append(f"📌 {home} é mais perigoso até agora.")
    if xg_away > xg_home:
        insights.append(f"📌 {away} gera mais perigo que o mandante.")
    if xg_h2_home + xg_h2_away > 0.7:
        insights.append("⏱ Intensidade crescente no segundo tempo.")

    return {
        "probabilities": {
            "over_1_5": round(p_over_1_5 * 100, 1),
            "over_2_5": round(p_over_2_5 * 100, 1),
            "under_2_5": round(p_under_2_5 * 100, 1),
            "btts": round(p_btts * 100, 1),
            "goal_h2": round(p_goal_h2 * 100, 1),
        },
        "odds": {
            "over_1_5": round(1 / p_over_1_5, 2),
            "over_2_5": round(1 / p_over_2_5, 2),
            "btts": round(1 / p_btts, 2) if p_btts else 0,
            "goal_h2": round(1 / p_goal_h2, 2) if p_goal_h2 else 0,
            "under_2_5": round(1 / p_under_2_5, 2) if p_under_2_5 else 0,
        },
        "projected_score": f"{projected_home:.1f} x {projected_away:.1f}",
        "recommendation": rec,
        "confidence": confidence,
        "insights": insights,
    }
