from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bet', '0004_possiblebet'),
    ]

    operations = [
        migrations.AddField(
            model_name='bankroll',
            name='initial_balance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]
