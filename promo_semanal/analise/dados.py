"""Consultas à base única. Abre a conexão só para ler e fecha em seguida,
para não travar a rotina de ingestão enquanto o painel está aberto."""
from __future__ import annotations

from contextlib import contextmanager

import duckdb
import pandas as pd

import config

_INICIO = config.DATA_INICIO_ANALISE


@contextmanager
def _con():
    con = duckdb.connect(str(config.BASE), read_only=True)
    try:
        yield con
    finally:
        con.close()


def versao_base() -> float:
    """Muda sempre que a base é gravada; serve de chave de cache no Streamlit."""
    return config.BASE.stat().st_mtime if config.BASE.exists() else 0.0


def consultar(sql: str, params: list | None = None) -> pd.DataFrame:
    with _con() as con:
        df = con.execute(sql, params or []).df()
    for c in ("data_tv", "data"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c]).dt.date
    return df


def programas_dia() -> pd.DataFrame:
    return consultar("SELECT data_tv, programa, rat, shr, fonte FROM programas_dia WHERE data_tv >= ?", [_INICIO])


def exibicoes() -> pd.DataFrame:
    return consultar("SELECT data_tv, emissora, programa, seq, hora_ini, hora_fim, min_ini, min_fim, "
                     "rat_abs, rat, shr, base, base_rank FROM exibicoes WHERE data_tv >= ?", [_INICIO])


def faixas(data_ini, data_fim) -> pd.DataFrame:
    return consultar("SELECT data_tv, minuto, rat_abs, rat, shr, base FROM faixas_minuto "
                     "WHERE emissora = ? AND data_tv BETWEEN ? AND ? ORDER BY data_tv, minuto",
                     [config.EMISSORA_PROPRIA, max(_INICIO, pd.Timestamp(data_ini).date()), data_fim])


def perfil(data_ini=None, data_fim=None) -> pd.DataFrame:
    if data_ini is None:
        return consultar("SELECT * EXCLUDE (arquivo) FROM perfil WHERE data_tv >= ?", [_INICIO])
    return consultar("SELECT * EXCLUDE (arquivo) FROM perfil WHERE data_tv BETWEEN ? AND ?",
                     [max(_INICIO, pd.Timestamp(data_ini).date()), data_fim])


def ocorrencias() -> pd.DataFrame:
    return consultar("SELECT * FROM ocorrencias WHERE data >= ?", [_INICIO])


def ultima_data(tabela: str = "programas_dia") -> pd.Timestamp | None:
    with _con() as con:
        v = con.execute(f"SELECT max(data_tv) FROM {tabela}").fetchone()[0]
    return v


def bases_por_dia(data_ini, data_fim) -> pd.DataFrame:
    """Para marcar dias 'prévia' (só Live) na interface."""
    return consultar("SELECT data_tv, max(base_rank) AS rank FROM exibicoes WHERE data_tv BETWEEN ? AND ? GROUP BY 1",
                     [data_ini, data_fim])


def log_ingestao(n: int = 30) -> pd.DataFrame:
    return consultar(f"SELECT * FROM log_ingestao ORDER BY quando DESC LIMIT {int(n)}")
