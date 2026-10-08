"""Perfil de público (Rat# por classe, idade e sexo): composição, afinidade, onde chamar e concorrência."""
from __future__ import annotations

import pandas as pd

import config

ORDEM_PUBLICOS = {
    "Classe": ["AB1", "B2", "C1", "C2", "DE"],
    "Idade": ["4-11 anos", "12-17 anos", "18-24 anos", "25-34 anos", "35-49 anos", "50-59 anos", "60+ anos"],
    "Sexo": ["HOMENS", "MULHERES"],
}


def _ponderado(p: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    """Rat# médio ponderado pela duração das exibições."""
    p = p.assign(dur=(p["min_fim"] - p["min_ini"]).clip(lower=1))
    p = p.assign(x=p["rat_abs"] * p["dur"])
    g = p.groupby(chaves + ["dimensao", "publico"]).agg(x=("x", "sum"), dur=("dur", "sum")).reset_index()
    g["rat_abs"] = g["x"] / g["dur"]
    return g.drop(columns=["x", "dur"])


def composicao(p: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    g = _ponderado(p, chaves)
    g["pct"] = g["rat_abs"] / g.groupby(chaves + ["dimensao"])["rat_abs"].transform("sum") * 100
    return g


def perfil_produto(p: pd.DataFrame, programas: list[str], ini, fim) -> pd.DataFrame:
    sel = p[p["programa"].isin(programas) & (p["emissora"] == config.EMISSORA_PROPRIA)
            & (p["data_tv"] >= ini) & (p["data_tv"] <= fim)]
    if sel.empty:
        return pd.DataFrame(columns=["dimensao", "publico", "rat_abs", "pct"])
    return composicao(sel.assign(k=1), ["k"]).drop(columns="k")


def perfil_globo(p: pd.DataFrame, ini, fim) -> pd.DataFrame:
    sel = p[(p["emissora"] == config.EMISSORA_PROPRIA) & (p["data_tv"] >= ini) & (p["data_tv"] <= fim)]
    return composicao(sel.assign(k=1), ["k"]).drop(columns="k")


def afinidade(prod: pd.DataFrame, globo: pd.DataFrame) -> pd.DataFrame:
    a = prod.merge(globo[["dimensao", "publico", "pct"]], on=["dimensao", "publico"], suffixes=("", "_globo"))
    a["afinidade"] = a["pct"] / a["pct_globo"] * 100
    a["ordem"] = a.apply(lambda r: ORDEM_PUBLICOS.get(r["dimensao"], []).index(r["publico"])
                         if r["publico"] in ORDEM_PUBLICOS.get(r["dimensao"], []) else 99, axis=1)
    return a.sort_values(["dimensao", "ordem"]).drop(columns="ordem")


def publicos_alvo(af: pd.DataFrame, dimensao: str, limiar: float = 110) -> list[str]:
    d = af[af["dimensao"] == dimensao]
    alvo = d[d["afinidade"] >= limiar]["publico"].tolist()
    return alvo or d.nlargest(1, "afinidade")["publico"].tolist()


def onde_chamar(p: pd.DataFrame, publicos: list[str], ini, fim, excluir: list[str] | None = None,
                top: int = 15, min_exibicoes: int = 3) -> pd.DataFrame:
    """Programas da Globo que mais entregam o público-alvo (soma do Rat# dos públicos escolhidos)."""
    sel = p[(p["emissora"] == config.EMISSORA_PROPRIA) & p["publico"].isin(publicos)
            & (p["data_tv"] >= ini) & (p["data_tv"] <= fim) & ~p["programa"].isin(excluir or [])]
    if sel.empty:
        return pd.DataFrame()
    # Rat# do público-alvo por exibição, depois média por programa
    por_exib = sel.groupby(["programa", "data_tv", "hora_ini", "min_ini", "min_fim"])["rat_abs"].sum().reset_index()
    por_exib["dia_semana"] = pd.to_datetime(por_exib["data_tv"]).dt.dayofweek
    r = por_exib.groupby("programa").agg(
        alvo_mil=("rat_abs", "mean"), exibicoes=("data_tv", "size"),
        hora_tipica=("hora_ini", lambda v: v.mode().iat[0][:5]),
        dias=("dia_semana", lambda v: sorted(set(v)))).reset_index()
    r = r[r["exibicoes"] >= min_exibicoes]  # tira avulsos (pronunciamento, flash, especial)
    # e o que já saiu da grade: precisa ter ido ao ar na última semana do período
    fim_ts = pd.Timestamp(fim).date()
    ativos = set(por_exib[por_exib["data_tv"] > fim_ts - pd.Timedelta(days=7)]["programa"])
    r = r[r["programa"].isin(ativos)]
    return r.sort_values("alvo_mil", ascending=False).head(top).reset_index(drop=True)


def concorrencia(p: pd.DataFrame, janelas: pd.DataFrame) -> pd.DataFrame:
    """Rat# por público de cada emissora durante as janelas do produto (data_tv, min_ini, min_fim).

    Cada programa concorrente pesa pelos minutos de sobreposição com a janela; o resultado
    é a audiência média por minuto de produto no ar.
    """
    linhas, minutos = [], 0
    for _, j in janelas.iterrows():
        d, a, b = j["data_tv"], int(j["min_ini"]), int(j["min_fim"])
        sel = p[(p["data_tv"] == d) & (p["min_fim"] > a) & (p["min_ini"] < b)].copy()
        if sel.empty:
            continue
        sel["sobrepos"] = sel["min_fim"].clip(upper=b) - sel["min_ini"].clip(lower=a)
        sel["x"] = sel["rat_abs"] * sel["sobrepos"]
        linhas.append(sel.groupby(["emissora", "dimensao", "publico"])["x"].sum().reset_index())
        minutos += b - a
    if not linhas:
        return pd.DataFrame()
    c = pd.concat(linhas).groupby(["emissora", "dimensao", "publico"])["x"].sum().reset_index()
    c["rat_abs"] = c.pop("x") / minutos
    c["pct"] = c["rat_abs"] / c.groupby(["emissora", "dimensao"])["rat_abs"].transform("sum") * 100
    return c
