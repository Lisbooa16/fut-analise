import json
from collections import defaultdict

from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from bet.teams.analytics import build_predictions, match_preview, team_profile
from jogos.models import Match, Team


def team_analysis_view(request, team_id):
    team = get_object_or_404(Team, id=team_id)

    matches = Match.objects.filter(home_team=team) | Match.objects.filter(
        away_team=team
    )

    stats_accumulator = defaultdict(list)

    for match in matches:
        if not match.raw_statistics_json:
            continue

        data = match.raw_statistics_json

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                continue

        if not isinstance(data, dict):
            continue

        side = "home" if match.home_team_id == team.id else "away"

        for block in data.get("statistics", []):
            if block.get("period") != "ALL":
                continue

            for group in block.get("groups", []):
                for item in group.get("statisticsItems", []):
                    key = item.get("key")

                    value = (
                        item.get("homeValue")
                        if side == "home"
                        else item.get("awayValue")
                    )

                    if isinstance(value, (int, float)):
                        stats_accumulator[key].append(value)

    aggregated = {
        key: {
            "avg": round(sum(values) / len(values), 2),
            "min": min(values),
            "max": max(values),
            "games": len(values),
        }
        for key, values in stats_accumulator.items()
    }

    predictions = build_predictions(aggregated)
    home_matches = Match.objects.filter(home_team=match.home_team, finalizado=True)
    away_matches = Match.objects.filter(away_team=match.away_team, finalizado=True)

    home_profile = team_profile(match.home_team, home_matches)
    away_profile = team_profile(match.away_team, away_matches)

    preview = match_preview(home_profile, away_profile)

    return render(
        request,
        "betting/team_analysis.html",
        {
            "team": team,
            "stats": aggregated,
            "matches_count": matches.count(),
            "predictions": predictions,
            "preview": preview,
        },
    )


def team_list_view(request):
    teams = (
        Team.objects.filter(
            Q(home_matches__finalizado=False) | Q(away_matches__finalizado=False)
        )
        .distinct()
        .order_by("name")
    )

    return render(
        request,
        "betting/team_list.html",
        {
            "teams": teams,
            "teams_count": teams.count(),
        },
    )


def match_preview_view(request, match_id):
    match = get_object_or_404(Match, id=match_id)

    RECENT_GAMES = 10

    # últimos jogos do mandante EM CASA
    home_matches = Match.objects.filter(
        Q(home_team=match.home_team) | Q(away_team=match.home_team),
        finalizado=True,
        date__lt=match.date,
    ).order_by("-date")[:RECENT_GAMES]

    away_matches = Match.objects.filter(
        Q(home_team=match.away_team) | Q(away_team=match.away_team),
        finalizado=True,
        date__lt=match.date,
    ).order_by("-date")[:RECENT_GAMES]

    home_profile = team_profile(match.home_team, home_matches)
    away_profile = team_profile(match.away_team, away_matches)

    preview = match_preview(home_profile, away_profile)

    return render(
        request,
        "betting/match_preview.html",
        {
            "match": match,
            "home": home_profile,
            "away": away_profile,
            "preview": preview,
            "sample_home": home_matches.count(),
            "sample_away": away_matches.count(),
        },
    )
