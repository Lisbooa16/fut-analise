from django.contrib import admin

from bet.models import AllowedLeague, Bankroll, BankrollHistory, Bet


class BankrollHistoryInline(admin.TabularInline):
    model = BankrollHistory
    extra = 0
    readonly_fields = ("status", "amount", "created_at", "note")
    ordering = ("-created_at",)


@admin.register(Bankroll)
class BankrollAdmin(admin.ModelAdmin):
    list_display = ("name", "balance", "initial_balance")
    search_fields = ("name",)
    inlines = (BankrollHistoryInline,)


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = (
        "match",
        "bankroll",
        "market",
        "odd",
        "stake",
        "potential_profit",
        "result",
        "created_at",
    )
    list_filter = ("result", "bankroll")
    search_fields = ("market", "match__home_team", "match__away_team")
    readonly_fields = ("potential_profit", "created_at")
    date_hierarchy = "created_at"


@admin.register(BankrollHistory)
class BankrollHistoryAdmin(admin.ModelAdmin):
    list_display = ("bankroll", "status", "amount", "created_at", "note")
    list_filter = ("status", "bankroll")
    search_fields = ("bankroll__name", "note")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"


@admin.register(AllowedLeague)
class AllowedLeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_editable = ("active",)
    search_fields = ("name",)
