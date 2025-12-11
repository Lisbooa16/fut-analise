import math

from django.contrib import admin, messages

from jogos.models import League, Match, MatchStats, RunningToday, Season, Team

# Register your models here.
admin.site.register(League)
admin.site.register(Season)
admin.site.register(Team)
admin.site.register(MatchStats)

import json

import requests
from django.contrib import admin

from .models import LiveSnapshot


def telegram_send(text: str):
    url = f"https://api.telegram.org/bot8087550191:AAHAA3C9lXWBGUFJWCR9jqPt1YfimDBX9Xk/sendMessage"

    payload = {
        "chat_id": "8426590050",
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Erro ao enviar mensagem para Telegram:", e)


def safe_json(value):
    """Garante que JSONField string vire dict."""
    if isinstance(value, dict) or isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


def parse_ratio(value: str, default_matches: int = 10) -> float:
    """
    Converte '5/7' -> 5/7, '8' -> 8/10 (~0.8), fallback 0.
    """
    if not isinstance(value, str):
        value = str(value)

    if "/" in value:
        try:
            num, den = value.split("/")
            num, den = int(num), int(den)
            if den == 0:
                return 0.0
            return max(0.0, min(1.0, num / den))
        except Exception:
            return 0.0

    try:
        num = int(value)
        return max(0.0, min(1.0, num / default_matches))
    except Exception:
        return 0.0


def score_from_streaks(items):
    """
    Gera um 'score de momento' pro time com base nas streaks.
    Valores maiores = momento melhor / jogos mais abertos.
    """
    score = 0.0

    for item in items:
        name = item.get("name", "").lower()
        value = item.get("value", "")
        r = parse_ratio(value)

        # Tendências ofensivas / jogos abertos
        if "more than 2.5 goals" in name:
            score += r * 4
        if "both teams scoring" in name:
            score += r * 4
        if "first to score" in name:
            score += r * 3

        # Defesa fraca (pode ser bom p/ gols, ruim p/ solidez do time)
        if "without clean sheet" in name:
            score += r * 2
        if "first to concede" in name:
            score -= r * 3
        if "no goals scored" in name:
            score -= r * 4
        if "losses" in name:
            score -= r * 2
        if "no wins" in name:
            score -= r * 2

    return score


def prob_label(p: float) -> str:
    """
    Texto bonitinho tipo: 'Alta (78%)'
    """
    p_pct = round(p * 100)
    if p >= 0.78:
        nivel = "Muito alta"
    elif p >= 0.65:
        nivel = "Alta"
    elif p >= 0.55:
        nivel = "Boa"
    elif p >= 0.45:
        nivel = "Equilibrada"
    else:
        nivel = "Baixa"
    return f"{nivel} ({p_pct}%)"


def analise_escanteios(general, h2h):
    # 1) Extrair métricas
    def get_ratio(name_substring, dataset):
        values = [
            parse_ratio(s["value"])
            for s in dataset
            if name_substring in s.get("name", "").lower()
        ]
        return max(values or [0.0])

    # Procurar padrões
    recent_over10 = get_ratio("more than 10.5 corners", general)
    h2h_over10 = get_ratio("more than 10.5 corners", h2h)

    # Se você quiser no futuro: more than 9.5, 11.5, etc.
    # Por enquanto assumimos que só 10.5 existe.

    # 2) Modelinho heurístico de probabilidade
    prob_over10 = (
        0.65 * recent_over10
        + 0.25 * h2h_over10
        + 0.10 * max(recent_over10, h2h_over10)  # reforço de tendência
    )
    prob_over10 = max(0, min(1, prob_over10))

    prob_under10 = 1 - prob_over10

    # 3) Insights textuais
    insights = []
    if prob_over10 >= 0.75:
        insights.append("Fortíssima tendência de *Over 10.5 escanteios*.")
    elif prob_over10 >= 0.60:
        insights.append("Boa tendência de *Over 10.5 escanteios*.")
    elif prob_over10 >= 0.50:
        insights.append("Tendência equilibrada para Over 10.5 cantos.")

    if recent_over10 >= 0.70:
        insights.append("Os jogos recentes das equipes têm gerado muitos escanteios.")

    if h2h_over10 >= 0.70:
        insights.append("O histórico direto indica partidas com muitos escanteios.")

    # Contradição
    contradicao = h2h_over10 <= 0.3 and recent_over10 >= 0.7

    if contradicao:
        insights.append(
            "O H2H indica poucos escanteios, mas o momento atual sugere jogo com bastante volume pelas laterais."
        )

    # 4) Sugestões de mercado
    sugestoes = []
    if prob_over10 >= 0.75:
        sugestoes.append(f"Over 10.5 escanteios – {prob_label(prob_over10)}")
    elif prob_over10 >= 0.60:
        sugestoes.append(f"Over 9.5 escanteios – {prob_label(prob_over10)}")

    if prob_under10 >= 0.65:
        sugestoes.append(f"Under 10.5 escanteios – {prob_label(prob_under10)}")

    return {
        "prob_over10": prob_over10,
        "prob_under10": prob_under10,
        "insights": insights,
        "sugestoes": sugestoes,
        "contradicao": contradicao,
    }


def gerar_analise_v3(match):
    # ---------- Dados básicos ----------
    event = safe_json(match.raw_event_json)
    streaks = safe_json(match.streaks_json)

    general = streaks.get("general", [])
    h2h = streaks.get("head2head", [])
    esc = analise_escanteios(general, h2h)

    home_name = event.get("homeTeam", {}).get(
        "name", getattr(match.home_team, "name", "Casa")
    )
    away_name = event.get("awayTeam", {}).get(
        "name", getattr(match.away_team, "name", "Fora")
    )
    tournament = event.get("tournament", {}).get("name", "Desconhecido")
    status = event.get("status", {}).get("description", "N/A")

    # ---------- Separar streaks ----------
    home_streaks = [s for s in general if s.get("team") == "home"]
    away_streaks = [s for s in general if s.get("team") == "away"]

    # ---------- Pontuação bruta ----------
    raw_home_score = score_from_streaks(home_streaks)
    raw_away_score = score_from_streaks(away_streaks)

    # ---------- Normalização (ESSENCIAL!) ----------
    # Converte score para uma escala [-1.5, +1.5]
    def normalize_score(x):
        return max(-1.5, min(1.5, x / 3))

    home_score = normalize_score(raw_home_score) + 0.2  # leve vantagem de mando
    away_score = normalize_score(raw_away_score)

    stronger = home_name if home_score > away_score else away_name

    # ---------- Softmax temperado (calibrado) ----------
    temperature = 2.2  # controla suavidade do softmax
    eh = math.exp(home_score / temperature)
    ed = math.exp((home_score + away_score) / 2 / temperature)
    ea = math.exp(away_score / temperature)

    total = eh + ed + ea
    p_home = eh / total
    p_draw = ed / total
    p_away = ea / total

    # ---------- Probabilidades Over/Under ----------
    recent_over = max(
        [parse_ratio(s["value"]) for s in general if "2.5" in s["name"].lower()] or [0]
    )
    h2h_over = max(
        [parse_ratio(s["value"]) for s in h2h if "2.5" in s["name"].lower()] or [0]
    )
    h2h_under = max(
        [parse_ratio(s["value"]) for s in h2h if "less than 2.5" in s["name"].lower()]
        or [0]
    )

    # Novo peso — mais realista:
    prob_over25 = 0.45 * recent_over + 0.45 * h2h_over + 0.10 * (1 - h2h_under)
    prob_over25 = max(0.05, min(0.95, prob_over25))
    prob_under25 = 1 - prob_over25

    # ---------- BTTS ----------
    recent_btts = max(
        [parse_ratio(s["value"]) for s in general if "both teams" in s["name"].lower()]
        or [0]
    )
    h2h_btts = max(
        [parse_ratio(s["value"]) for s in h2h if "both teams" in s["name"].lower()]
        or [0]
    )

    prob_btts = 0.5 * recent_btts + 0.5 * h2h_btts
    prob_btts = max(0.05, min(0.95, prob_btts))

    # ---------- Quem marca primeiro ----------
    away_first = max(
        [
            parse_ratio(s["value"])
            for s in general
            if s.get("team") == "away" and "first to score" in s["name"].lower()
        ]
        or [0]
    )
    home_first = max(
        [
            parse_ratio(s["value"])
            for s in general
            if s.get("team") == "home" and "first to score" in s["name"].lower()
        ]
        or [0]
    )
    home_first_concede = max(
        [
            parse_ratio(s["value"])
            for s in general
            if s.get("team") == "home" and "first to concede" in s["name"].lower()
        ]
        or [0]
    )

    # Nova fórmula calibrada:
    raw_away_first = (
        0.55 * away_first + 0.25 * home_first_concede + 0.20 * (1 - home_first)
    )
    prob_away_first = max(0.10, min(0.90, raw_away_first))
    prob_home_first = 1 - prob_away_first

    # ---------- Contradições ----------
    contradicao_h2h_gols = h2h_under >= 0.7 and prob_over25 >= 0.6

    # ---------- Insights ----------
    insights = []

    # momento
    if away_score > home_score + 0.6:
        insights.append(f"{away_name} chega em fase claramente superior.")
    elif away_score > home_score:
        insights.append(f"{away_name} chega em leve melhor fase.")
    elif home_score > away_score + 0.6:
        insights.append(f"{home_name} chega em fase claramente superior.")
    else:
        insights.append("Momento relativamente equilibrado entre as equipes.")

    # padrões
    if prob_btts >= 0.65:
        insights.append("Boa tendência para *Ambas Marcam (BTTS)*.")
    if prob_over25 >= 0.65:
        insights.append("Boa tendência de *Over 2.5 gols*.")
    if prob_under25 >= 0.65:
        insights.append("Tendência para *Under 2.5 gols*.")
    if prob_away_first >= 0.60:
        insights.append(f"Tendência de {away_name} marcar o primeiro gol.")
    elif prob_home_first >= 0.60:
        insights.append(f"Tendência de {home_name} marcar o primeiro gol.")

    if contradicao_h2h_gols:
        insights.append(
            "H2H indica poucos gols, mas o momento recente sugere jogo mais aberto."
        )

    # ---------- Sugestões ----------
    sugestoes = []
    if prob_over25 > 0.70:
        sugestoes.append(f"Over 2.5 gols – {prob_label(prob_over25)}")
    if prob_btts > 0.70:
        sugestoes.append(f"BTTS – {prob_label(prob_btts)}")
    if p_away > 0.55:
        sugestoes.append(f"{away_name} DNB – {prob_label(p_away)}")
    elif p_home > 0.55:
        sugestoes.append(f"{home_name} DNB – {prob_label(p_home)}")

    # ---------- RESUMO FINAL ----------
    resumo = f"""
    📊 *Análise Automática V3.1 (calibrada)*

        *{home_name}* vs *{away_name}*
        Campeonato: *{tournament}*
        Status: `{status}`

        *Força do Momento*
        - {home_name}: `{home_score:.2f}`
        - {away_name}: `{away_score:.2f}`
        🔥 Mais forte: *{stronger}*

        *Probabilidades*
        - Vitória {home_name}: {prob_label(p_home)}
        - Empate: {prob_label(p_draw)}
        - Vitória {away_name}: {prob_label(p_away)}

        - Over 2.5: {prob_label(prob_over25)}
        - Under 2.5: {prob_label(prob_under25)}
        - BTTS: {prob_label(prob_btts)}
        - Primeiro gol {home_name}: {prob_label(prob_home_first)}
        - Primeiro gol {away_name}: {prob_label(prob_away_first)}

        *Escanteios*
        - Over 10.5: {prob_label(esc["prob_over10"])}
        - Under 10.5: {prob_label(esc["prob_under10"])}

        *Insights*
        {chr(10).join(f"- {i}" for i in insights)}

        *Mercados fortes* (não é recomendação)
        {chr(10).join(f"- {s}" for s in sugestoes) or "- Nenhum mercado forte."}
    """.strip()

    return {
        "home_score": home_score,
        "away_score": away_score,
        "stronger": stronger,
        "prob_result": {"home_win": p_home, "draw": p_draw, "away_win": p_away},
        "prob_over25": prob_over25,
        "prob_under25": prob_under25,
        "prob_btts": prob_btts,
        "prob_first_goal": {"home": prob_home_first, "away": prob_away_first},
        "contradicao_h2h_gols": contradicao_h2h_gols,
        "insights": insights,
        "sugestoes": sugestoes,
        "resumo": resumo,
    }


def gerar_analise_v2(match):
    event = safe_json(match.raw_event_json)
    streaks = safe_json(match.streaks_json)

    general = streaks.get("general", [])
    h2h = streaks.get("head2head", [])

    home_name = event.get("homeTeam", {}).get("name", match.home_team.name)
    away_name = event.get("awayTeam", {}).get("name", match.away_team.name)
    tournament = event.get("tournament", {}).get("name", "Desconhecido")
    status = event.get("status", {}).get("description", "N/A")

    # ---- PONTUAÇÃO ----
    home_streaks = [s for s in general if s.get("team") == "home"]
    away_streaks = [s for s in general if s.get("team") == "away"]

    home_score = score_from_streaks(home_streaks)
    away_score = score_from_streaks(away_streaks)

    # força relativa
    if home_score > away_score:
        stronger = home_name
    else:
        stronger = away_name

    # ---- TENDÊNCIAS ----
    tendencia_over25 = any("2.5" in s.get("name", "").lower() for s in general + h2h)
    tendencia_btts = any("both teams" in s.get("name", "").lower() for s in general)
    tendencia_first = any(
        "first to score" in s.get("name", "").lower() for s in general
    )

    # ---- CONTRADIÇÕES ----
    contradicao_h2h = False
    if (
        any("less than 2.5" in s.get("name", "").lower() for s in h2h)
        and tendencia_over25
    ):
        contradicao_h2h = True

    # ---- INSIGHTS ----
    insights = []

    if away_score > home_score:
        insights.append(f"{away_name} chega em momento superior.")
    if tendencia_btts:
        insights.append("Ambas marcam aparece como tendência forte.")
    if tendencia_over25:
        insights.append("Jogos recentes sugerem boa probabilidade de Over 2.5.")
    if tendencia_first:
        insights.append("Há tendência clara para um dos times marcar primeiro.")
    if contradicao_h2h:
        insights.append(
            "O H2H histórico sugere poucos gols, mas o momento atual indica jogo mais aberto."
        )

    # resumo final
    resumo = (
        f"*{home_name}* vs *{away_name}* — análise automática\n"
        f"*Campeonato:* {tournament}\n"
        f"*Status:* {status}\n\n"
        f"📊 *Força do momento*\n"
        f"- {home_name}: `{home_score}`\n"
        f"- {away_name}: `{away_score}`\n"
        f"- 🔥 Time mais forte no momento: *{stronger}*\n\n"
        f"🎯 *Insights principais*\n" + "\n".join(f"- {i}" for i in insights)
    )

    return {
        "home_score": home_score,
        "away_score": away_score,
        "stronger": stronger,
        "tendencia_over25": tendencia_over25,
        "tendencia_btts": tendencia_btts,
        "tendencia_first_goal": tendencia_first,
        "contradicao_h2h": contradicao_h2h,
        "insights": insights,
        "resumo": resumo,
    }


def gerar_analise(match):
    event = safe_json(match.raw_event_json)
    streaks = safe_json(match.streaks_json)

    home = event.get("homeTeam", {}).get("name", match.home_team.name)
    away = event.get("awayTeam", {}).get("name", match.away_team.name)
    tournament = event.get("tournament", {}).get("name", "Desconhecido")
    status = event.get("status", {}).get("description", "N/A")

    general = streaks.get("general", [])
    h2h = streaks.get("head2head", [])

    def build_section(lst):
        lines = []
        for item in lst:
            team = (
                "Casa"
                if item.get("team") == "home"
                else "Fora" if item.get("team") == "away" else "Ambos"
            )
            lines.append(f"- *{team}*: {item.get('name')} `{item.get('value')}`")
        return "\n".join(lines)

    analise_text = f"""
        *📊 Análise Automática da Partida*

        *{home}* vs *{away}*
        Campeonato: *{tournament}*
        Status: `{status}`

        *🔥 Tendências Gerais*
        {build_section(general)}

        *⚔️ Confrontos Diretos*
        {build_section(h2h)}
    """

    # objeto completo salvo no model
    analise_json = {
        "partida": f"{home} vs {away}",
        "campeonato": tournament,
        "status": status,
        "tendencias_gerais": general,
        "confrontos_diretos": h2h,
    }

    return analise_json, analise_text


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "external_id",
        "home_team",
        "away_team",
        "date",
        "finalizado",
        "current_minute",
    )
    actions = [
        "gerar_analise_e_enviar",
        "action_gerar_analise_v2",
        "gerar_analise_v3_action",
        "set_nao_finalizado",
    ]

    list_filter = (
        "finalizado",
        "season",
        "home_team",
        "away_team",
        "tournament_id",
    )

    search_fields = (
        "external_id",
        "home_team__name",
        "away_team__name",
        "slug",
    )

    ordering = ("-date",)

    readonly_fields = ("created_at",)

    fieldsets = (
        (
            "Informações da Partida",
            {
                "fields": (
                    "season",
                    "external_id",
                    "slug",
                    "home_team",
                    "away_team",
                    "date",
                    "finalizado",
                    "current_minute",
                    "home_team_score",
                    "away_team_score",
                )
            },
        ),
        (
            "IDs Técnicos",
            {
                "fields": (
                    "tournament_id",
                    "season_ids",
                    "home_id",
                    "away_id",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Dados Internos (JSON)",
            {
                "fields": (
                    "insights",
                    "previsao_automatica",
                    "raw_event_json",
                    "raw_statistics_json",
                    "event_json",
                    "stading_json",
                    "stats_json",
                    "streaks_json",
                    "analise",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadados",
            {
                "fields": ("created_at",),
            },
        ),
    )

    # Para permitir edição mais confortável dos JSONs
    from django.db import models
    from django.forms import Textarea

    formfield_overrides = {
        models.JSONField: {"widget": Textarea(attrs={"rows": 4, "cols": 80})},
    }

    def gerar_analise_e_enviar(self, request, queryset):
        enviados = 0

        for match in queryset:
            analise_json, analise_text = gerar_analise(match)

            # salva no banco
            match.analise = analise_json
            match.save(update_fields=["analise"])

            # envia para telegram
            telegram_send(analise_text)

            enviados += 1

        self.message_user(
            request,
            f"Análises geradas e enviadas para o Telegram ({enviados} jogo(s))!",
        )

    def action_gerar_analise_v2(self, request, queryset):
        enviados = 0

        for match in queryset:
            analise = gerar_analise_v2(match)
            match.analise = analise
            match.save(update_fields=["analise"])

            telegram_send(analise["resumo"])
            enviados += 1

        self.message_user(
            request,
            f"Análises avançadas geradas e enviadas para {enviados} jogo(s)!",
            level=messages.SUCCESS,
        )

    def gerar_analise_v3_action(self, request, queryset):
        count = 0

        for match in queryset:
            analise = gerar_analise_v3(match)
            match.analise = analise
            match.save(update_fields=["analise"])

            telegram_send(analise["resumo"])
            count += 1

        self.message_user(
            request,
            f"Análise V3 gerada e enviada para {count} jogo(s).",
            level=messages.SUCCESS,
        )

    def set_nao_finalizado(self, request, queryset):
        for match in queryset:
            match.finalizado = False
            match.save(update_fields=["finalizado"])

        self.message_user(
            request,
            f"Não finalizado jogo(s).",
            level=messages.SUCCESS,
        )

    gerar_analise_v3_action.short_description = (
        "Gerar análise V3 + enviar para o Telegram"
    )
    set_nao_finalizado.short_description = "Não Finalizada"

    action_gerar_analise_v2.short_description = (
        "Gerar análise avançada V2 + enviar Telegram"
    )

    gerar_analise_e_enviar.short_description = "Gerar análise e enviar para o Telegram"


@admin.register(LiveSnapshot)
class LiveSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "match",
        "minute",
        "xg_home",
        "xg_away",
        "shots_on_home",
        "shots_on_away",
        "corners_home",
        "corners_away",
        "momentum_score",
        "created_at",
    )

    list_filter = (
        "match",
        "minute",
        "created_at",
    )

    search_fields = (
        "match__home_team__name",
        "match__away_team__name",
        "match__id",
    )

    ordering = ("match", "minute")

    readonly_fields = ("created_at",)

    fieldsets = (
        (
            "Informações básicas",
            {
                "fields": (
                    "match",
                    "minute",
                    "created_at",
                    "momentum_score",
                )
            },
        ),
        (
            "Ofensivo Principal",
            {
                "fields": (
                    ("xg_home", "xg_away"),
                    ("shots_on_home", "shots_on_away"),
                    ("shots_total_home", "shots_total_away"),
                    ("corners_home", "corners_away"),
                    ("possession_home", "possession_away"),
                )
            },
        ),
        (
            "Profundidade Ofensiva",
            {
                "fields": (
                    ("touches_box_home", "touches_box_away"),
                    ("final_third_entries_home", "final_third_entries_away"),
                    ("big_chances_home", "big_chances_away"),
                    ("big_chances_missed_home", "big_chances_missed_away"),
                    ("shots_inside_box_home", "shots_inside_box_away"),
                    ("shots_outside_box_home", "shots_outside_box_away"),
                )
            },
        ),
        (
            "Defensivo",
            {
                "fields": (
                    ("interceptions_home", "interceptions_away"),
                    ("clearances_home", "clearances_away"),
                    ("recoveries_home", "recoveries_away"),
                    ("tackles_won_home", "tackles_won_away"),
                )
            },
        ),
        (
            "Goalkeeping",
            {
                "fields": (
                    ("saves_home", "saves_away"),
                    ("goals_prevented_home", "goals_prevented_away"),
                )
            },
        ),
        (
            "Disciplina",
            {
                "fields": (
                    ("fouls_home", "fouls_away"),
                    ("yellow_home", "yellow_away"),
                    ("red_home", "red_away"),
                )
            },
        ),
    )


admin.site.register(RunningToday)
