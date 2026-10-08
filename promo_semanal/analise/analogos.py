"""Dias análogos: como cada produto se comportou em datas parecidas no passado."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

TIPOS_ANALOGOS = ["Feriado nacional", "Feriado estadual", "Feriado municipal", "Ponto facultativo",
                  "Data comemorativa", "Acontecimento"]


def datas_analogas(ev: pd.DataFrame, alvo: date, primeira_data: date) -> list[dict]:
    """Para cada evento de calendário do dia-alvo, as datas passadas do mesmo evento.

    Eventos com data fixa (mesmo dia/mês em todas as ocorrências) são estendidos para
    todos os anos com dados de audiência (desde `primeira_data`).
    """
    alvo = pd.Timestamp(alvo).date()
    hoje_ev = ev[(ev["data"] == alvo) & ev["categoria"].isin(TIPOS_ANALOGOS)]
    saida = []
    for _, e in hoje_ev.drop_duplicates("titulo").iterrows():
        mesmas = ev[(ev["titulo"] == e["titulo"]) & (ev["data"] < alvo)]["data"].tolist()
        todas = mesmas + [alvo]
        fixa = len({(d.month, d.day) for d in todas}) == 1
        if fixa:
            for ano in range(primeira_data.year, alvo.year):
                try:
                    mesmas.append(date(ano, alvo.month, alvo.day))
                except ValueError:
                    pass
        for d in sorted(set(mesmas), reverse=True):
            if d >= primeira_data:
                saida.append({"evento": e["titulo"], "categoria": e["categoria"], "data_analoga": d})
    return saida


def impacto_produto(prod_diario: pd.DataFrame, produto: str, data_ref: date, datas_excluir: set,
                    n_semanas: int = 4) -> dict:
    """Rat% do produto na data contra a média do mesmo dia da semana nas n semanas anteriores."""
    p = prod_diario[prod_diario["produto"] == produto].set_index("data_tv")
    base_datas = [data_ref - timedelta(weeks=k) for k in range(1, n_semanas + 1)]
    base = p.loc[[d for d in base_datas if d in p.index and d not in datas_excluir], "rat"]
    exibiu = data_ref in p.index
    rat = p.loc[data_ref, "rat"] if exibiu else None
    habitual = len(base) > 0  # o produto costuma ir ao ar nesse dia da semana
    return {
        "produto": produto, "data": data_ref, "exibido": exibiu, "dia_habitual": habitual,
        "rat": rat, "rat_base": base.mean() if habitual else None,
        "delta_pct": (rat / base.mean() - 1) * 100 if exibiu and habitual and base.mean() else None,
        "inicio": p.loc[data_ref, "min_ini"] if exibiu and "min_ini" in p.columns else None,
    }


def tabela_analogos(ev: pd.DataFrame, prod_diario: pd.DataFrame, produtos_do_dia: dict[date, list[str]],
                    primeira_data: date) -> pd.DataFrame:
    """Uma linha por (dia-alvo, data análoga, produto).

    produtos_do_dia: para cada dia-alvo, os produtos que costumam ir ao ar nesse dia da semana.
    """
    excluir = set(ev[ev["categoria"].isin(TIPOS_ANALOGOS[:4])]["data"])
    linhas = []
    for alvo, produtos in produtos_do_dia.items():
        analogas = pd.DataFrame(datas_analogas(ev, alvo, primeira_data))
        if analogas.empty:
            continue
        # um dia com dois eventos (ex.: 12/10) vira uma linha só por data análoga
        analogas = analogas.groupby("data_analoga")["evento"].agg(lambda v: " / ".join(dict.fromkeys(v)))
        for d_an, evento in analogas.sort_index(ascending=False).items():
            for prod in produtos:
                imp = impacto_produto(prod_diario, prod, d_an, excluir)
                if not imp["exibido"] and not imp["dia_habitual"]:
                    continue  # nesse ano o produto não ia ao ar nesse dia da semana
                linhas.append({"dia_alvo": alvo, "evento": evento, "data_analoga": d_an, **imp})
    t = pd.DataFrame(linhas)
    if not t.empty:
        t["dia_semana_analoga"] = pd.to_datetime(t["data_analoga"]).dt.dayofweek
    return t
