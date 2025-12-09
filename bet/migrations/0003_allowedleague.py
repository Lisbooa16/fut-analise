from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bet", "0002_bankrollhistory"),
    ]

    operations = [
        migrations.CreateModel(
            name="AllowedLeague",
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
                ("name", models.CharField(max_length=100, unique=True)),
                (
                    "active",
                    models.BooleanField(
                        default=True,
                        help_text="Se desmarcado, a liga será ignorada no scraping.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Liga Permitida",
                "verbose_name_plural": "Ligas Permitidas",
            },
        ),
    ]
