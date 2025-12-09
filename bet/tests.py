from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from bet.models import Bankroll, Bet, Status
from jogos.models import League, Match, Season, Team


class BankrollTestCase(TestCase):
    def setUp(self):
        self.bankroll = Bankroll.objects.create(name="Teste", balance=Decimal("100"))

    def test_deposit_and_withdraw_register_history(self):
        self.bankroll.deposit(Decimal("25"), note="Depósito de teste")
        self.bankroll.withdraw(Decimal("10"), note="Saque de teste")

        self.bankroll.refresh_from_db()

        self.assertEqual(self.bankroll.balance, Decimal("115"))
        self.assertEqual(self.bankroll.history.count(), 2)
        self.assertIn(
            Status.INCREASE, self.bankroll.history.values_list("status", flat=True)
        )
        self.assertIn(
            Status.DECREASE, self.bankroll.history.values_list("status", flat=True)
        )

    def test_withdraw_prevents_negative_balance(self):
        with self.assertRaises(ValueError):
            self.bankroll.withdraw(Decimal("200"))


class BetSettlementTestCase(TestCase):
    def setUp(self):
        self.bankroll = Bankroll.objects.create(name="Teste", balance=Decimal("50"))
        league = League.objects.create(country="BR", name="Serie Teste")
        season = Season.objects.create(
            league=league, name="Temporada Teste", external_id=1
        )
        home = Team.objects.create(league=league, name="Time A", external_id=1)
        away = Team.objects.create(league=league, name="Time B", external_id=2)

        self.match = Match.objects.create(
            season=season,
            external_id=1,
            home_team=home,
            away_team=away,
            date=timezone.now(),
            tournament_id="1",
            season_ids="1",
            home_id="1",
            away_id="2",
        )

    def test_settle_bet_updates_bankroll_once(self):
        bet = Bet.objects.create(
            bankroll=self.bankroll,
            match=self.match,
            market="Teste",
            odd=Decimal("2.0"),
            stake=Decimal("10"),
        )

        bet.register_bet()
        self.bankroll.refresh_from_db()
        self.assertEqual(self.bankroll.balance, Decimal("40"))

        bet.settle_bet(is_green=True)
        self.bankroll.refresh_from_db()
        self.assertEqual(self.bankroll.balance, Decimal("50"))
        self.assertEqual(bet.result, "GREEN")

        with self.assertRaises(ValueError):
            bet.settle_bet(is_green=True)
