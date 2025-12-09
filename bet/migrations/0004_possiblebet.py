from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bet", "0003_allowedleague"),
    ]

    operations = [
        migrations.CreateModel(
            name="PossibleBet",
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
                ("event_id", models.CharField(max_length=50)),
                ("market", models.CharField(max_length=255)),
                ("probability", models.PositiveIntegerField(default=50)),
                ("description", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
