import calendar

from django.core.management.base import BaseCommand

from bet.models import PossibleBet
from get_events import SofaScore
from jogos.utils import save_sofascore_data
import requests
import json
from datetime import date, timedelta

BASE = "https://www.sofascore.com/api/v1"
headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


class Command(BaseCommand):
    help = "Busca dados do Sofascore e salva no banco"

    def get_month_days(self, year, month):
        first = date(year, month, 1)

        # se for dezembro, próximo mês é janeiro do próximo ano
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)

        days = []
        current = first

        while current < next_month:
            days.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        return days

    def handle(self, *args, **options):
        year, month = 2025, 11
        num_days = calendar.monthrange(year, month)[1]
        date = [
            f"{year}-{month:02d}-{day:02d}"
            for day in range(1, num_days + 1)
        ]
        # date = ['2025-12-03']
        self.stdout.write("🚀 Rodando Sofascore... Eventos")
        event = SofaScore().get_stats(13472780)
        # print(SofaScore().get_stadings(77805, 62, 3056, 3050))
        self.stdout.write("🚀 Eventos Finalizado")