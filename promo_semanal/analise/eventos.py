"""Eventos relevantes para a grade local: feriados, datas, acontecimentos e futebol do Brasil."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd

import config

COMPETICOES_BR = {
    "Brazilian Serie A": "Série A",
    "Brazilian Serie B": "Série B",
    "Copa do Brasil": "Copa do Brasil",
    "CONMEBOL Libertadores": "Libertadores",
    "CONMEBOL Sudamericana": "Sudamericana",
    "Brazilian Campeonato Paulista": "Paulistão",
    "FIFA World Cup": "Copa do Mundo",
    "FIFA Club World Cup": "Mundial de Clubes",
    "FIFA World Cup Qualifying - CONMEBOL": "Eliminatórias",
    "Copa América": "Copa América",
}
TIPOS_CALENDARIO = ["Feriado nacional", "Feriado estadual", "Feriado municipal", "Ponto facultativo",
                    "Data comemorativa", "Acontecimento"]
ICONE = {"Feriado nacional": "🟥", "Feriado estadual": "🟥", "Feriado municipal": "🟥", "Ponto facultativo": "🟧",
         "Data comemorativa": "🟦", "Acontecimento": "🟪", "Futebol": "⚽"}


def carregar_times() -> dict[str, str]:
    t = pd.read_csv(config.TIMES_CSV)
    return dict(zip(t["time"], t["grupo"]))


def eventos_relevantes(ocorrencias: pd.DataFrame, times: dict[str, str] | None = None) -> pd.DataFrame:
    """Filtra as ocorrências para o que importa à grade local e padroniza as colunas."""
    times = times or carregar_times()
    o = ocorrencias
    cal = o[o["tipo"].isin(TIPOS_CALENDARIO)].copy()
    cal["categoria"] = cal["tipo"]
    cal["destaque"] = cal["tipo"].str.startswith("Feriado") | (cal["tipo"] == "Acontecimento")
    cal["grupo"] = ""

    fut = o[o["tipo"] == "Futebol"].copy()
    eh_br = fut["competicao"].isin(COMPETICOES_BR) | fut["mandante"].isin(["Brazil"]) | fut["visitante"].isin(["Brazil"])
    fut = fut[eh_br].copy()
    fut["categoria"] = "Futebol"
    fut["competicao_pt"] = fut["competicao"].map(COMPETICOES_BR).fillna(fut["competicao"])
    # grupo do jogo = o mais relevante entre mandante e visitante (Seleção > Região > SP)
    prioridade = {"Seleção": 0, "Região": 1, "SP": 2}
    grupos = pd.concat([fut["mandante"].map(times), fut["visitante"].map(times)], axis=1)
    fut["grupo"] = grupos.apply(lambda r: min((x for x in r if isinstance(x, str)),
                                              key=lambda x: prioridade.get(x, 9), default=""), axis=1)
    fut["destaque"] = fut["grupo"] != ""
    fut["titulo"] = fut["competicao_pt"] + " · " + fut["titulo"]

    cols = ["data", "categoria", "titulo", "abrangencia", "horario", "grupo", "destaque", "status"]
    ev = pd.concat([cal.reindex(columns=cols), fut.reindex(columns=cols)], ignore_index=True)
    ev["icone"] = ev["categoria"].map(ICONE).fillna("•")
    ev["horario"] = ev["horario"].fillna("")
    return ev.sort_values(["data", "categoria", "horario"]).reset_index(drop=True)


def eventos_periodo(ev: pd.DataFrame, ini, fim, so_destaque_futebol: bool = True) -> pd.DataFrame:
    ini, fim = pd.Timestamp(ini).date(), pd.Timestamp(fim).date()
    e = ev[(ev["data"] >= ini) & (ev["data"] <= fim)]
    if so_destaque_futebol:
        e = e[(e["categoria"] != "Futebol") | e["destaque"]]
    return e


def eventos_semana(ev: pd.DataFrame, seg, so_destaque_futebol: bool = True) -> pd.DataFrame:
    seg = pd.Timestamp(seg).date()
    return eventos_periodo(ev, seg, seg + timedelta(days=6), so_destaque_futebol)


def datas_marcadas(ev: pd.DataFrame, so_atipicas: bool = False) -> dict:
    """data -> rótulo do evento de calendário (feriado/ponto facultativo/acontecimento).

    so_atipicas=True fica só com o que mexe com a grade inteira: feriados, pontos facultativos e
    acontecimentos de abrangência nacional (ex.: eleições). Eventos locais como a Expoflora ficam de fora.
    """
    e = ev[ev["categoria"].str.startswith("Feriado") | ev["categoria"].isin(["Ponto facultativo", "Acontecimento"])]
    if so_atipicas:
        nacional = e["abrangencia"].fillna("").str.startswith("Brasil")
        e = e[(e["categoria"] != "Acontecimento") | nacional]
    return e.groupby("data")["titulo"].agg(lambda v: " / ".join(dict.fromkeys(v))).to_dict()
