from django.db import models
from django.utils import timezone
from django.utils.timezone import now


class League(models.Model):
    country = models.CharField(max_length=255)
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.name} ({self.country})"


class Season(models.Model):
    league = models.ForeignKey(
        League, on_delete=models.CASCADE, related_name="seasons"
    )
    name = models.CharField(max_length=255)
    external_id = models.IntegerField(null=True, blank=True)  # SofaScore seasonId

    def __str__(self):
        return f"{self.name} - {self.league.name}"


class Team(models.Model):
    league = models.ForeignKey(
        League, on_delete=models.CASCADE, related_name="teams"
    )
    name = models.CharField(max_length=255)
    external_id = models.IntegerField(null=True, blank=True)  # SofaScore teamId

    def __str__(self):
        return self.name


class Match(models.Model):
    season = models.ForeignKey(
        Season, on_delete=models.CASCADE, related_name="matches"
    )
    external_id = models.IntegerField(unique=True)  # eventId do SofaScore
    slug = models.CharField(max_length=255, null=True, blank=True)

    home_team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="home_matches"
    )
    away_team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="away_matches"
    )

    date = models.DateTimeField(null=True, blank=True)
    finalizado = models.BooleanField(default=False)

    home_team_score = models.IntegerField(null=True, blank=True)
    away_team_score = models.IntegerField(null=True, blank=True)

    # Insights textuais + previsão
    insights = models.JSONField(default=list, blank=True)
    previsao_automatica = models.JSONField(default=dict, blank=True)
    raw_event_json = models.JSONField(default=dict, blank=True)
    raw_statistics_json = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    current_minute = models.IntegerField(default=0)
    tournament_id = models.CharField(max_length=255)
    season_ids = models.CharField(max_length=255)
    home_id = models.CharField(max_length=255)
    away_id = models.CharField(max_length=255)
    event_json = models.JSONField(default=dict, blank=True)
    stading_json = models.JSONField(default=dict, blank=True)
    stats_json = models.JSONField(default=dict, blank=True)
    streaks_json = models.JSONField(default=dict, blank=True)
    analise = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.home_team} vs {self.away_team}"

class RunningToday(models.Model):
    rodou = models.BooleanField(default=False)
    data = models.DateField(db_index=True)

class MatchStats(models.Model):
    match = models.OneToOneField(
        Match, on_delete=models.CASCADE, related_name="stats"
    )

    # --- Estatísticas SofaScore
    xg_home = models.FloatField(default=0)
    xg_away = models.FloatField(default=0)
    possession_home = models.FloatField(default=0)
    possession_away = models.FloatField(default=0)

    shots_home = models.IntegerField(default=0)
    shots_away = models.IntegerField(default=0)
    shots_on_home = models.IntegerField(default=0)
    shots_on_away = models.IntegerField(default=0)

    corners_home = models.IntegerField(default=0)
    corners_away = models.IntegerField(default=0)

    fouls_home = models.IntegerField(default=0)
    fouls_away = models.IntegerField(default=0)

    yellow_home = models.IntegerField(default=0)
    yellow_away = models.IntegerField(default=0)

    # --- Métricas extras
    pressure_home = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    pressure_away = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    danger_home = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    danger_away = models.DecimalField(max_digits=6, decimal_places=3, default=0)

    summary = models.TextField(null=True, blank=True)
    analyzed_at = models.DateTimeField(default=now)

    team_home = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='stats_home',
        null=True, blank=True
    )

    team_away = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='stats_away',
        null=True, blank=True
    )

    score_home = models.IntegerField(null=True, blank=True)
    score_away = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"Stats {self.match}"


class TeamStreak(models.Model):
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="streaks"
    )

    group = models.CharField(max_length=50)  # general / head2head
    name = models.CharField(max_length=255)
    team = models.CharField(max_length=20)  # home / away / both
    raw_value = models.CharField(max_length=20)

    ratio = models.FloatField(null=True, blank=True)
    hot = models.BooleanField(default=False)
    intensity = models.CharField(max_length=20, null=True, blank=True)
    insight = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.team})"


class StandingEntry(models.Model):
    match = models.OneToOneField(
        Match, on_delete=models.CASCADE, related_name="standings"
    )

    home_position = models.IntegerField(null=True, blank=True)
    home_points = models.IntegerField(null=True, blank=True)
    home_wins = models.IntegerField(null=True, blank=True)
    home_draws = models.IntegerField(null=True, blank=True)
    home_losses = models.IntegerField(null=True, blank=True)
    home_goals_for = models.IntegerField(null=True, blank=True)
    home_goals_against = models.IntegerField(null=True, blank=True)
    home_goal_diff = models.CharField(max_length=5, null=True, blank=True)
    home_is_top = models.BooleanField(default=False)
    home_is_relegation = models.BooleanField(default=False)

    away_position = models.IntegerField(null=True, blank=True)
    away_points = models.IntegerField(null=True, blank=True)
    away_wins = models.IntegerField(null=True, blank=True)
    away_draws = models.IntegerField(null=True, blank=True)
    away_losses = models.IntegerField(null=True, blank=True)
    away_goals_for = models.IntegerField(null=True, blank=True)
    away_goals_against = models.IntegerField(null=True, blank=True)
    away_goal_diff = models.CharField(max_length=5, null=True, blank=True)
    away_is_top = models.BooleanField(default=False)
    away_is_relegation = models.BooleanField(default=False)

    favorito = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Standings {self.match}"


class LiveSnapshot(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    minute = models.IntegerField()

    # ======== OFENSIVO PRINCIPAL ========
    xg_home = models.FloatField()
    xg_away = models.FloatField()

    shots_on_home = models.IntegerField()
    shots_on_away = models.IntegerField()

    shots_total_home = models.IntegerField()
    shots_total_away = models.IntegerField()

    corners_home = models.IntegerField()
    corners_away = models.IntegerField()

    possession_home = models.FloatField()
    possession_away = models.FloatField()

    # ======== PROFUNDIDADE OFENSIVA ========
    touches_box_home = models.IntegerField()
    touches_box_away = models.IntegerField()

    final_third_entries_home = models.IntegerField()
    final_third_entries_away = models.IntegerField()

    big_chances_home = models.IntegerField(default=0)
    big_chances_away = models.IntegerField(default=0)

    big_chances_missed_home = models.IntegerField(default=0)
    big_chances_missed_away = models.IntegerField(default=0)

    shots_inside_box_home = models.IntegerField(default=0)
    shots_inside_box_away = models.IntegerField(default=0)

    shots_outside_box_home = models.IntegerField(default=0)
    shots_outside_box_away = models.IntegerField(default=0)

    # ======== DEFENSIVO ========
    interceptions_home = models.IntegerField(default=0)
    interceptions_away = models.IntegerField(default=0)

    clearances_home = models.IntegerField(default=0)
    clearances_away = models.IntegerField(default=0)

    recoveries_home = models.IntegerField(default=0)
    recoveries_away = models.IntegerField(default=0)

    tackles_won_home = models.IntegerField(default=0)
    tackles_won_away = models.IntegerField(default=0)

    # ======== GOALKEEPING ========
    saves_home = models.IntegerField(default=0)
    saves_away = models.IntegerField(default=0)

    goals_prevented_home = models.FloatField(default=0)
    goals_prevented_away = models.FloatField(default=0)

    # ======== DISCIPLINA ========
    fouls_home = models.IntegerField(default=0)
    fouls_away = models.IntegerField(default=0)

    yellow_home = models.IntegerField(default=0)
    yellow_away = models.IntegerField(default=0)

    red_home = models.IntegerField(default=0)
    red_away = models.IntegerField(default=0)

    # ======== SCORE DINÂMICO ========
    momentum_score = models.FloatField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["minute"]