import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from jogos.models import Match


class Command(BaseCommand):
    help = "Atualiza partidas com dados e análise do Flashscore (finaliza e remove duplicadas)."

    def handle(self, *args, **options):
        while True:
            self.stdout.write(
                "🔄 Atualizando partidas com dados e análises do Flashscore..."
            )
            self.update_matches()
            self.stdout.write("🕒 Aguardando 1 minuto...\n")
            time.sleep(60)

    def update_matches(self):
        now = timezone.now()
        updated = 0

        # ⚽ Atualiza partidas (tempo e expiração)
        matches = Match.objects.all()

        for m in matches:
            finalizado_original = m.finalizado

            # 1️⃣ Finaliza por tempo (90+)
            if str(m.date).strip() in ["90+", "91", "92", "93", "94", "95"]:
                m.finalizado = True

            # 2️⃣ Finaliza jogos muito antigos (sem atualização há +2h)
            if (
                hasattr(m, "created_at")
                and m.created_at
                and (now - m.created_at) > timedelta(hours=2)
            ):
                m.finalizado = True

            # 3️⃣ Salva apenas se mudou
            if m.finalizado and not finalizado_original:
                m.save(update_fields=["finalizado"])
                updated += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✅ {m} marcado como finalizado.")
                )

        # 4️⃣ Trata duplicadas (mesmo home_team, away_team, date)
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        duplicates = (
            Match.objects.filter(created_at__range=(today_start, today_end))
            .values("home_team", "away_team")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
        )

        duplicates_count = 0
        for dup in duplicates:
            # pega todos os jogos iguais de hoje
            dups = Match.objects.filter(
                home_team=dup["home_team"],
                away_team=dup["away_team"],
                created_at__range=(today_start, today_end),
            ).order_by(
                "-id"
            )  # mantém o mais recente

            # Mantém o mais recente e finaliza os outros
            to_finalize = dups[1:]
            for m in to_finalize:
                if not m.finalizado:
                    m.finalizado = True
                    m.save(update_fields=["finalizado"])
                    duplicates_count += 1
                    self.stdout.write(
                        self.style.WARNING(f"🧩 Duplicado de hoje finalizado: {m}")
                    )

        # 🧾 Logs de resumo
        if updated == 0 and duplicates_count == 0:
            self.stdout.write(
                "⚠️ Nenhuma partida precisou ser atualizada ou finalizada."
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"🏁 {updated} partidas finalizadas por tempo.")
            )
            self.stdout.write(
                self.style.WARNING(f"♻️ {duplicates_count} duplicadas finalizadas.")
            )
