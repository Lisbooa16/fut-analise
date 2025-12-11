from django.urls import path

from . import views
from .views import MatchOddsFeaturedView

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("matches/", views.matches_list, name="matches_list"),
    path("matches/<int:pk>/", views.match_detail, name="match_detail"),
    path("matches/<int:match_id>/bet/", views.place_bet, name="place_bet"),
    path("bankroll/", views.bankroll_view, name="bankroll_view"),
    path("bet/<int:bet_id>/update/", views.update_bet_result, name="update_bet_result"),
    path("check_result/", views.result, name="result_betting"),
    path("analise/", views.match_analysis, name="match_analysis"),
    path(
        "bet/create-from-model/<int:pb_id>/",
        views.create_bet_from_model,
        name="create_bet_from_model",
    ),
    path("post-status/", views.post_status, name="post-data-stats"),
    path(
        "matches/<int:match_id>/snapshots/",
        views.match_snapshots,
        name="match_snapshots",
    ),
    path("run-scraper/", views.sofascore_scrape_view, name="run_scraper"),
    path("matches/<int:pk>/odds/featured/", MatchOddsFeaturedView.as_view()),
]
