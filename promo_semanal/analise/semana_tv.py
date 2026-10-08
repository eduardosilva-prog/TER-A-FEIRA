"""Calendário de TV: dia de 06:00 a 29:59 e semana de segunda a domingo."""
from datetime import date, timedelta

import pandas as pd

INICIO_DIA_TV = 6 * 60  # 06:00
DIAS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
DIAS_PT_LONGO = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def hora_para_minuto(h) -> int:
    """'06:00:00' -> 0, '25:30:00' -> 1170. Horas >= 24 seguem no mesmo dia de TV."""
    partes = str(h).strip().split(":")
    return int(partes[0]) * 60 + int(partes[1]) - INICIO_DIA_TV


def minuto_para_hora(m: int) -> str:
    """Inverso de hora_para_minuto, no formato da grade (ex.: 25:30)."""
    t = int(m) + INICIO_DIA_TV
    return f"{t // 60:02d}:{t % 60:02d}"


def segunda(d) -> date:
    d = pd.Timestamp(d).date()
    return d - timedelta(days=d.weekday())


def segundas(serie: pd.Series) -> pd.Series:
    s = pd.to_datetime(serie)
    return (s - pd.to_timedelta(s.dt.dayofweek, unit="D")).dt.date


def rotulo_semana(seg) -> str:
    seg = pd.Timestamp(seg).date()
    fim = seg + timedelta(days=6)
    return f"S{seg.isocalendar().week:02d} · {seg:%d/%m}–{fim:%d/%m/%Y}"


def ultima_semana_completa(ultima_data) -> date:
    """Segunda-feira da última semana cujo domingo já está na base."""
    d = pd.Timestamp(ultima_data).date()
    seg = segunda(d)
    return seg if d.weekday() == 6 else seg - timedelta(days=7)


def proxima_semana(hoje=None) -> date:
    hoje = pd.Timestamp(hoje or date.today()).date()
    return segunda(hoje) + timedelta(days=7)


def dias_da_semana(seg) -> list[date]:
    seg = pd.Timestamp(seg).date()
    return [seg + timedelta(days=i) for i in range(7)]
