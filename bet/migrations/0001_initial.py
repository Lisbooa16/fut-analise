import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("jogos", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Bankroll",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                (
                    "balance",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
            ],
        ),
        migrations.CreateModel(
            name="BetSlip",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("total_stake", models.DecimalField(decimal_places=2, max_digits=10)),
                ("total_odd", models.DecimalField(decimal_places=2, max_digits=6)),
                (
                    "potential_profit",
                    models.DecimalField(decimal_places=2, max_digits=10),
                ),
                (
                    "result",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pendente"),
                            ("GREEN", "Green"),
                            ("RED", "Red"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "bankroll",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="bet.bankroll"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Bet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("market", models.CharField(max_length=255)),
                ("odd", models.DecimalField(decimal_places=2, max_digits=6)),
                ("stake", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "potential_profit",
                    models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                (
                    "result",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pendente"),
                            ("GREEN", "Green"),
                            ("RED", "Red"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "bankroll",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bets",
                        to="bet.bankroll",
                    ),
                ),
                (
                    "match",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bets",
                        to="jogos.match",
                    ),
                ),
            ],
        ),
    ]
