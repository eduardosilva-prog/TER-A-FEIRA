"""Minuto a minuto: curva dos produtos, blocos de 15 min e janelas para chamadas."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

import config
from analise.semana_tv import minuto_para_hora

BLOCO = 15
JANELA_ENTORNO = 5  # minutos de lead-in / lead-out


def blocos(fx: pd.DataFrame, tamanho: int = BLOCO) -> pd.DataFrame:
    """Rat% médio por dia × bloco."""
    f = fx.assign(bloco=fx["minuto"] // tamanho * tamanho)
    b = f.groupby(["data_tv", "bloco"]).agg(rat=("rat", "mean"), rat_abs=("rat_abs", "mean")).reset_index()
    b["dia_semana"] = pd.to_datetime(b["data_tv"]).dt.dayofweek
    return b


def programa_no_minuto(exib: pd.DataFrame, datas, minutos: np.ndarray) -> pd.DataFrame:
    """Qual programa da Globo estava no ar em cada (data, minuto)."""
    e = exib[(exib["emissora"] == config.EMISSORA_PROPRIA) & exib["data_tv"].isin(set(datas))]
    linhas = []
    for d, g in e.groupby("data_tv"):
        g = g.sort_values("min_ini")
        idx = np.searchsorted(g["min_ini"].to_numpy(), minutos, side="right") - 1
        nomes = g["programa"].to_numpy()
        fim = g["min_fim"].to_numpy()
        for m, i in zip(minutos, idx):
            if i >= 0 and m < fim[i]:
                linhas.append((d, m, nomes[i]))
    return pd.DataFrame(linhas, columns=["data_tv", "minuto", "programa"])


def heatmap_semana_tipica(fx: pd.DataFrame, exib: pd.DataFrame, excluir_datas: set | None = None) -> pd.DataFrame:
    """Dia da semana × bloco: Rat% médio e programa mais frequente no meio do bloco."""
    excluir = set(excluir_datas or set())
    dias_sem = pd.to_datetime(pd.Series(fx["data_tv"].unique())).dt.dayofweek
    restantes = {d for d, ds in zip(fx["data_tv"].unique(), dias_sem) if d not in excluir}
    restantes_dow = {pd.Timestamp(d).dayofweek for d in restantes}
    # nunca deixa um dia da semana sem dado: se todos foram excluídos, mantém esse dia
    excluir = {d for d in excluir if pd.Timestamp(d).dayofweek in restantes_dow}
    f = fx[~fx["data_tv"].isin(excluir)]
    b = blocos(f)
    media = b.groupby(["dia_semana", "bloco"]).agg(rat=("rat", "mean"), rat_abs=("rat_abs", "mean"),
                                                    n_dias=("data_tv", "nunique")).reset_index()
    meio = np.arange(0, 1440, BLOCO) + BLOCO // 2
    pm = programa_no_minuto(exib, b["data_tv"].unique(), meio)
    if not pm.empty:
        pm["dia_semana"] = pd.to_datetime(pm["data_tv"]).dt.dayofweek
        pm["bloco"] = pm["minuto"] // BLOCO * BLOCO
        tipico = pm.groupby(["dia_semana", "bloco"])["programa"].agg(lambda v: v.mode().iat[0]).rename("programa")
        media = media.merge(tipico.reset_index(), on=["dia_semana", "bloco"], how="left")
    else:
        media["programa"] = ""
    media["hora"] = media["bloco"].map(minuto_para_hora)
    return media


def curva_exibicoes(fx: pd.DataFrame, segmentos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Para cada dia em que o produto foi ao ar: curva relativa ao início e indicadores.

    segmentos: uma linha por exibição (data_tv, min_ini, min_fim). Um produto pode ser
    partido no dia (ex.: JE1 interrompido pelo horário eleitoral); minutos fora dos
    segmentos não contam como produto.
    """
    curvas, ind = [], []
    for d, seg in segmentos.groupby("data_tv"):
        a, b = int(seg["min_ini"].min()), int(seg["min_fim"].max())
        f = fx[(fx["data_tv"] == d) & (fx["minuto"] >= a - JANELA_ENTORNO) & (fx["minuto"] < b + JANELA_ENTORNO)]
        if f.empty:
            continue
        no_ar = np.zeros(len(f), dtype=bool)
        for _, s in seg.iterrows():
            no_ar |= (f["minuto"] >= s["min_ini"]).to_numpy() & (f["minuto"] < s["min_fim"]).to_numpy()
        c = f[["minuto", "rat", "shr"]].copy()
        c["rel"] = c["minuto"] - a
        c["no_ar"] = no_ar
        c["data_tv"] = d
        curvas.append(c)
        dentro = f[no_ar]
        antes = f[f["minuto"] < a]
        depois = f[f["minuto"] >= b]
        abertura = dentro.head(JANELA_ENTORNO)["rat"].mean()
        fechamento = dentro.tail(JANELA_ENTORNO)["rat"].mean()
        pico = dentro.loc[dentro["rat"].idxmax()] if not dentro.empty else None
        ind.append({
            "data_tv": d, "inicio": minuto_para_hora(a), "fim": minuto_para_hora(b),
            "duracao": int(no_ar.sum()), "blocos": len(seg),
            "lead_in": antes["rat"].mean(), "abertura": abertura, "media": dentro["rat"].mean(),
            "pico": None if pico is None else pico["rat"],
            "hora_pico": None if pico is None else minuto_para_hora(pico["minuto"]),
            "fechamento": fechamento, "lead_out": depois["rat"].mean(),
            "retencao": fechamento / abertura * 100 if abertura else None,
            "heranca": abertura / antes["rat"].mean() * 100 if len(antes) and antes["rat"].mean() else None,
        })
    return (pd.concat(curvas, ignore_index=True) if curvas else pd.DataFrame(),
            pd.DataFrame(ind))


def melhores_blocos_antes(heat: pd.DataFrame, dias_exibicao: list[int], hora_ini_tipica: dict[int, int],
                          dias_antes: int = 3, top: int = 10) -> pd.DataFrame:
    """Blocos com maior Rat% nos dias que antecedem cada exibição (e no próprio dia, antes do início)."""
    linhas = []
    for dia in sorted(set(dias_exibicao)):
        for k in range(0, dias_antes + 1):
            alvo = (dia - k) % 7
            h = heat[heat["dia_semana"] == alvo]
            if k == 0:
                h = h[h["bloco"] + BLOCO <= hora_ini_tipica.get(dia, 1440)]
            linhas.append(h.assign(dias_antes=k, dia_exibicao=dia))
    if not linhas:
        return pd.DataFrame()
    j = pd.concat(linhas).sort_values("rat", ascending=False)
    j = j.drop_duplicates(["dia_semana", "bloco"])
    return j.head(top).reset_index(drop=True)
