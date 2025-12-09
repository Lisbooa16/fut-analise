from django.contrib import admin

from bet.models import Bankroll, Bet, BankrollHistory, AllowedLeague

# Register your models here.
admin.site.register(Bankroll)
admin.site.register(Bet)
admin.site.register(BankrollHistory)

@admin.register(AllowedLeague)
class AllowedLeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_editable = ("active",)
    search_fields = ("name",)