"""Agregados semanais (padrão BASE_SEMANAL) e comparativos dos produtos locais.

Regras confirmadas contra a BASE_SEMANAL_V1_RF:
- Rat% e Shr% semanais = média simples dos dias em que o programa foi ao ar;
- Exibições = dias com exibição na semana; Dias base = dias com dados na semana;
- Exib habituais = mediana arredondada das exibições semanais do programa (todo o histórico);
- Completa = 7 dias base; Comparável = Completa e Exibições >= 60% das habituais.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

import config
from analise.semana_tv import segundas

CLASSES = ["Reforçar", "Aproveitar", "Estável", "Atípico", "Sem exibição"]


def _arred(x: pd.Series) -> pd.Series:
    # arredondamento bancário (2,5 -> 2), igual ao da BASE_SEMANAL original
    return np.round(x).astype(int)


def semanal(diario: pd.DataFrame, chave: str = "programa", extras: list[str] | None = None) -> pd.DataFrame:
    """diario: data_tv, <chave>, rat, shr [, extras]. Devolve uma linha por semana × chave."""
    d = diario.copy()
    d["semana"] = segundas(d["data_tv"])
    dias_base = d.groupby("semana")["data_tv"].nunique().rename("dias_base")
    agg = {"rat": ("rat", "mean"), "shr": ("shr", "mean"), "exibicoes": ("data_tv", "nunique")}
    for c in extras or []:
        agg[c] = (c, "mean")
    s = d.groupby(["semana", chave]).agg(**agg).reset_index().merge(dias_base, on="semana")
    s["exib_habituais"] = s.groupby(chave)["exibicoes"].transform(lambda v: _arred(v.median()))
    s["completa"] = s["dias_base"] == 7
    s["comparavel"] = s["completa"] & (s["exibicoes"] / s["exib_habituais"] >= config.LIMIAR_COMPARAVEL)
    s["fim_semana"] = s["semana"] + timedelta(days=6)
    return s.sort_values(["semana", chave]).reset_index(drop=True)


def semanal_formato_referencia(programas_dia: pd.DataFrame) -> pd.DataFrame:
    """BASE_SEMANAL no mesmo layout do arquivo original."""
    s = semanal(programas_dia)
    return pd.DataFrame({
        "Semana": pd.to_datetime(s["semana"]).dt.strftime("%d/%m/%Y"),
        "Fim semana": pd.to_datetime(s["fim_semana"]).dt.strftime("%d/%m/%Y"),
        "Nome Programa": s["programa"],
        "Rat%": s["rat"].round(2),
        "Shr%": s["shr"].round(2),
        "Exibições": s["exibicoes"],
        "Exib habituais": s["exib_habituais"],
        "Dias base": s["dias_base"],
        "Completa": s["completa"],
        "Comparável": s["comparavel"],
    })


# ---------------------------------------------------------------- produtos locais

def carregar_produtos() -> pd.DataFrame:
    return pd.read_csv(config.PRODUTOS_CSV)


def ordem_produtos(produtos: pd.DataFrame) -> list[str]:
    return produtos.sort_values("ordem").drop_duplicates("produto")["produto"].tolist()


def produtos_diario(programas_dia: pd.DataFrame, exibicoes: pd.DataFrame, produtos: pd.DataFrame,
                    tipo: str = "principal") -> pd.DataFrame:
    """Uma linha por dia × produto: rat, shr (padrão HISTORICA), rat_abs, horário e nº de exibições."""
    mapa = produtos[produtos["tipo"] == tipo][["produto", "programa"]]
    pdia = programas_dia.merge(mapa, on="programa")
    d = pdia.groupby(["data_tv", "produto"]).agg(rat=("rat", "mean"), shr=("shr", "mean"),
                                               programas=("programa", lambda v: " + ".join(sorted(set(v))))).reset_index()
    e = exibicoes[exibicoes["emissora"] == config.EMISSORA_PROPRIA].merge(mapa, on="programa")
    if not e.empty:
        e = e.assign(dur=(e["min_fim"] - e["min_ini"]).clip(lower=1))
        e["rat_abs_x"] = e["rat_abs"] * e["dur"]
        ex = e.groupby(["data_tv", "produto"]).agg(
            rat_abs_x=("rat_abs_x", "sum"), dur=("dur", "sum"), min_ini=("min_ini", "min"),
            min_fim=("min_fim", "max"), n_exib=("programa", "size"), base_rank=("base_rank", "min")).reset_index()
        ex["rat_abs"] = ex["rat_abs_x"] / ex["dur"]
        d = d.merge(ex.drop(columns=["rat_abs_x"]), on=["data_tv", "produto"], how="left")
    else:
        for c in ["rat_abs", "dur", "min_ini", "min_fim", "n_exib", "base_rank"]:
            d[c] = np.nan
    d["dia_semana"] = pd.to_datetime(d["data_tv"]).dt.dayofweek
    return d


def produtos_semanal(prod_diario: pd.DataFrame, programas_dia: pd.DataFrame) -> pd.DataFrame:
    s = semanal(prod_diario.rename(columns={"produto": "prog"}), chave="prog", extras=["rat_abs"])
    s = s.rename(columns={"prog": "produto"})
    # dias base vêm da base inteira, não só dos dias com produto
    dias_base = programas_dia.assign(semana=segundas(programas_dia["data_tv"])).groupby("semana")["data_tv"].nunique()
    s["dias_base"] = s["semana"].map(dias_base).fillna(s["dias_base"]).astype(int)
    s["completa"] = s["dias_base"] == 7
    s["comparavel"] = s["completa"] & (s["exibicoes"] / s["exib_habituais"] >= config.LIMIAR_COMPARAVEL)
    return s


def comparativos(sem: pd.DataFrame, semana, produtos_ordem: list[str], lim_pct: float = 10.0,
                 lim_pt: float = 0.5, n_media: int = 4, marcas_atipico: dict | None = None) -> pd.DataFrame:
    """Uma linha por produto com a semana, os três comparativos e a classificação para Promo."""
    semana = pd.Timestamp(semana).date()
    ant = semana - timedelta(days=7)
    ano = semana - timedelta(days=364)
    linhas = []
    for prod in produtos_ordem:
        s = sem[sem["produto"] == prod].set_index("semana")
        atual = s.loc[semana] if semana in s.index else None
        hist = s[(s.index < semana) & s["comparavel"]].tail(n_media)
        linha = {"produto": prod}
        for nome, ref in [("ant", s.loc[ant] if ant in s.index else None),
                          ("ano", s.loc[ano] if ano in s.index else None)]:
            for m in ["rat", "shr"]:
                linha[f"{m}_{nome}"] = None if ref is None else ref[m]
        for m in ["rat", "shr", "rat_abs"]:
            linha[m] = None if atual is None else atual[m]
            linha[f"{m}_media{n_media}"] = hist[m].mean() if len(hist) else None
        linha["exibicoes"] = None if atual is None else int(atual["exibicoes"])
        linha["exib_habituais"] = None if atual is None else int(atual["exib_habituais"])
        linha["comparavel"] = None if atual is None else bool(atual["comparavel"])
        for nome, base in [("ant", "rat_ant"), ("media", f"rat_media{n_media}"), ("ano", "rat_ano")]:
            a, b = linha["rat"], linha[base]
            ok = a is not None and b is not None and pd.notna(a) and pd.notna(b) and b != 0
            linha[f"d_pt_{nome}"] = a - b if ok else None
            linha[f"d_pct_{nome}"] = (a / b - 1) * 100 if ok else None
        linha["serie"] = s[s.index <= semana]["rat"].tail(12).round(2).tolist()
        linha["classe"], linha["motivo"] = _classificar(linha, lim_pct, lim_pt, (marcas_atipico or {}).get(prod))
        linhas.append(linha)
    out = pd.DataFrame(linhas)
    num = [c for c in out.columns if c not in ("produto", "serie", "classe", "motivo", "comparavel")]
    out[num] = out[num].astype(float)  # None -> NaN (vazio nas tabelas)
    return out


def _classificar(l: dict, lim_pct: float, lim_pt: float, marca: str | None) -> tuple[str, str]:
    if l["rat"] is None or pd.isna(l["rat"]):
        return "Sem exibição", "não foi ao ar na semana"
    if not l["comparavel"]:
        return "Atípico", f"{int(l['exibicoes'])} de {int(l['exib_habituais'])} exibições habituais"
    if marca:
        return "Atípico", marca
    dpt, dpct = l["d_pt_media"], l["d_pct_media"]
    if dpt is None:
        return "Estável", "sem histórico comparável"
    if abs(dpct) >= lim_pct and abs(dpt) >= lim_pt:
        return ("Reforçar", "abaixo da média recente") if dpt < 0 else ("Aproveitar", "acima da média recente")
    return "Estável", "dentro da faixa usual"


def horario_deslocado(prod_diario: pd.DataFrame, semana, tolerancia_min: int = 30) -> dict:
    """Produtos cuja hora de início na semana fugiu da mediana das 8 semanas anteriores."""
    semana = pd.Timestamp(semana).date()
    d = prod_diario.dropna(subset=["min_ini"]).copy()
    d["semana"] = segundas(d["data_tv"])
    marcas = {}
    for prod, g in d.groupby("produto"):
        atual = g[g["semana"] == semana]
        hist = g[(g["semana"] < semana) & (g["semana"] >= semana - timedelta(weeks=8))]
        if atual.empty or hist.empty:
            continue
        ref = hist.groupby("dia_semana")["min_ini"].median()
        desvio = (atual.set_index("dia_semana")["min_ini"] - ref).dropna().abs()
        if (desvio > tolerancia_min).any():
            marcas[prod] = "horário deslocado"
    return marcas


def segmentos_produto(exib: pd.DataFrame, produtos: pd.DataFrame, produto: str, ini, fim,
                      tipo: str = "principal") -> pd.DataFrame:
    """Cada exibição (bloco) do produto no período: data_tv, programa, min_ini, min_fim, rat, rat_abs."""
    nomes = produtos[(produtos["produto"] == produto) & (produtos["tipo"] == tipo)]["programa"]
    e = exib[(exib["emissora"] == config.EMISSORA_PROPRIA) & exib["programa"].isin(nomes)
             & (exib["data_tv"] >= ini) & (exib["data_tv"] <= fim)]
    return e.sort_values(["data_tv", "min_ini"]).reset_index(drop=True)


def dias_habituais(prod_diario: pd.DataFrame, produto: str, ref, semanas: int = 8, minimo: float = 0.5) -> list[int]:
    """Dias da semana (0=seg) em que o produto foi ao ar em pelo menos metade das últimas semanas."""
    ref = pd.Timestamp(ref).date()
    p = prod_diario[(prod_diario["produto"] == produto) & (prod_diario["data_tv"] < ref)
                    & (prod_diario["data_tv"] >= ref - timedelta(weeks=semanas))]
    freq = p.groupby("dia_semana")["data_tv"].nunique() / semanas
    return sorted(freq[freq >= minimo].index.tolist())


def hora_tipica(prod_diario: pd.DataFrame, produto: str, ref, semanas: int = 8) -> dict[int, int]:
    """Minuto de início mediano por dia da semana nas últimas semanas."""
    ref = pd.Timestamp(ref).date()
    p = prod_diario[(prod_diario["produto"] == produto) & (prod_diario["data_tv"] < ref)
                    & (prod_diario["data_tv"] >= ref - timedelta(weeks=semanas))].dropna(subset=["min_ini"])
    return p.groupby("dia_semana")["min_ini"].median().astype(int).to_dict()
