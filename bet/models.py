from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import models, transaction

from jogos.models import Match


class Status(models.IntegerChoices):
    INCREASE = 1, "Depósito"
    DECREASE = 2, "Retirada"


class Bankroll(models.Model):
    name = models.CharField(max_length=255)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    initial_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.name} - R$ {self.balance}"

    def _apply_movement(self, amount: Decimal | str, status: int, note: str | None = None):
        """Aplica movimentações de forma atômica e registra histórico."""

        try:
            decimal_amount = Decimal(amount)
        except (InvalidOperation, TypeError):
            raise ValueError("Valor inválido para movimentação.")

        if decimal_amount <= 0:
            raise ValueError("Movimentações precisam ser maiores que zero.")

        if self.pk is None:
            raise ValueError("A banca precisa ser salva antes de registrar movimentações.")

        with transaction.atomic():
            bankroll = Bankroll.objects.select_for_update().get(pk=self.pk)

            if status == Status.DECREASE and bankroll.balance < decimal_amount:
                raise ValueError("Saldo insuficiente na banca!")

            updated_balance = (
                bankroll.balance + decimal_amount
                if status == Status.INCREASE
                else bankroll.balance - decimal_amount
            )
            bankroll.balance = updated_balance
            bankroll.save(update_fields=["balance"])

            history = BankrollHistory.objects.create(
                bankroll=bankroll,
                status=status,
                amount=decimal_amount,
                note=note,
            )

        self.balance = updated_balance
        return history

    def deposit(self, amount, note: str | None = None):
        return self._apply_movement(amount, Status.INCREASE, note)

    def withdraw(self, amount, note: str | None = None):
        return self._apply_movement(amount, Status.DECREASE, note)

class BankrollHistory(models.Model):

    bankroll = models.ForeignKey(
        'Bankroll',
        on_delete=models.CASCADE,
        related_name='history'
    )
    status = models.IntegerField(choices=Status.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        direction = "↑" if self.status == Status.INCREASE else "↓"
        return f"{direction} R$ {self.amount:.2f} — {self.get_status_display()}"

    class Meta:
        verbose_name = "Movimentação da Banca"
        verbose_name_plural = "Histórico da Banca"
        ordering = ["-created_at"]

class Bet(models.Model):
    bankroll = models.ForeignKey(
        'Bankroll', on_delete=models.CASCADE, related_name='bets'
    )
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name='bets'
    )
    market = models.CharField(max_length=255)  # Ex: "+1.5 gols", "Vitória do Palmeiras"
    odd = models.DecimalField(max_digits=6, decimal_places=2)
    stake = models.DecimalField(max_digits=10, decimal_places=2)  # valor apostado
    potential_profit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    result = models.CharField(
        max_length=20,
        choices=[('PENDING', 'Pendente'), ('GREEN', 'Green'), ('RED', 'Red')],
        default='PENDING'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def calculated_potential_profit(self):
        """Lucro esperado SE a aposta for green"""
        return (self.stake * self.odd) - self.stake

    def __str__(self):
        return f"{self.match} | {self.market} ({self.result})"

    def calculate_profit(self):
        """Calcula o possível retorno."""
        return round(self.stake * self.odd, 2)

    def register_bet(self):
        """Registra aposta e debita da banca de forma consistente."""

        with transaction.atomic():
            bankroll = Bankroll.objects.select_for_update().get(pk=self.bankroll_id)
            self.potential_profit = self.calculate_profit()
            bankroll.withdraw(self.stake, note=f"Aposta em {self.match} ({self.market})")
            bankroll.refresh_from_db(fields=["balance"])
            self.save()

    def settle_bet(self, is_green: bool):
        """Atualiza o resultado e ajusta saldo da banca com proteção contra duplicidade."""

        if self.result != 'PENDING':
            raise ValueError("A aposta já foi liquidada.")

        with transaction.atomic():
            bet = Bet.objects.select_for_update().get(pk=self.pk)
            if bet.result != 'PENDING':
                raise ValueError("A aposta já foi liquidada.")

            if is_green:
                bet.result = 'GREEN'
                bet.bankroll.deposit(
                    bet.potential_profit or bet.calculate_profit(),
                    note=f"Green: {bet.match} ({bet.market})",
                )
            else:
                bet.result = 'RED'

            bet.save(update_fields=["result"])
            self.result = bet.result

class BetSlip(models.Model):
    bankroll = models.ForeignKey('Bankroll', on_delete=models.CASCADE)
    total_stake = models.DecimalField(max_digits=10, decimal_places=2)
    total_odd = models.DecimalField(max_digits=6, decimal_places=2)
    potential_profit = models.DecimalField(max_digits=10, decimal_places=2)
    result = models.CharField(
        max_length=20,
        choices=[('PENDING', 'Pendente'), ('GREEN', 'Green'), ('RED', 'Red')],
        default='PENDING'
    )
    created_at = models.DateTimeField(auto_now_add=True)


class AllowedLeague(models.Model):
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True, help_text="Se desmarcado, a liga será ignorada no scraping.")

    class Meta:
        verbose_name = "Liga Permitida"
        verbose_name_plural = "Ligas Permitidas"

    def __str__(self):
        return self.name

class PossibleBet(models.Model):
    event_id = models.CharField(max_length=50)
    market = models.CharField(max_length=255)
    probability = models.PositiveIntegerField(default=50)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.market} ({self.probability}%)"
