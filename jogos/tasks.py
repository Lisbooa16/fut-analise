from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from get_events import SofaScore

from .models import Match

# from django.forms.models import model_to_dict # Geralmente não precisamos disso no celery, a menos que vá salvar em log JSON


@shared_task
def process_match_snapshot(event_id):
    """
    Esta tarefa faz o trabalho pesado: busca stats e analisa.
    Substitui a lógica interna da sua view.
    """
    try:
        match = Match.objects.get(id=event_id)

        # 1. Busca os dados (Snapshot)
        snapshot = SofaScore().get_stats(event_id)

        if snapshot is None:
            print(f"Erro: Nenhum snapshot criado para a match {event_id}")
            return "No snapshot"

        # 2. Realiza a análise
        analysis_live = SofaScore().analyze_last_snapshots(match, window=10)

        # 3. O QUE FAZER COM OS DADOS?
        # No Celery você não retorna JsonResponse. Você deve SALVAR no banco ou enviar notificação.
        # Exemplo: Atualizar o objeto Match ou salvar um novo registro de Log

        # Exemplo hipotético de salvamento:
        # match.last_analysis = analysis_live
        # match.save()

        print(f"Sucesso: Match {event_id} analisada. Dados: {analysis_live}")
        return "Success"

    except Match.DoesNotExist:
        print(f"Match {event_id} não encontrada.")
    except Exception as e:
        print(f"Erro na task da match {event_id}: {str(e)}")
        # Opcional: Re-raise para o Celery tentar novamente se configurado
        # raise e


@shared_task
def dispatch_todays_matches():
    """
    Esta tarefa busca as partidas e dispara o processamento para cada uma.
    Critérios: Hoje, Não finalizada, Horário > Agora.
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999)

    # Filtrando as partidas
    matches = Match.objects.filter(
        date__date=now.date(),  # Era 'start_time', seu model usa 'date'
        finalizado=False,  # Era 'finished', seu model usa 'finalizado'
    )

    if not matches.exists():
        print("Nenhuma partida encontrada nos critérios.")
        return

    print(f"Encontradas {matches.count()} partidas para processar.")

    for match in matches:
        # Dispara a tarefa assíncrona para cada jogo
        process_match_snapshot.delay(match.id)
