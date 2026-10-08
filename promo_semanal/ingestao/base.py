"""Base única em DuckDB: esquema, upsert por dia e derivação de programas_dia.

Regra de substituição: cada data é substituída inteira quando o lote novo tem
prioridade igual ou maior que a existente (Consolidado > Live; referência > derivado).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

import config
from ingestao.leitores import Ignorado, Lote, ler_arquivo

ESQUEMA = """
CREATE TABLE IF NOT EXISTS exibicoes (
    data_tv DATE, emissora VARCHAR, programa VARCHAR, seq INTEGER,
    hora_ini VARCHAR, hora_fim VARCHAR, min_ini INTEGER, min_fim INTEGER,
    rat_abs DOUBLE, rat DOUBLE, shr DOUBLE, base VARCHAR, base_rank INTEGER, arquivo VARCHAR);
CREATE TABLE IF NOT EXISTS faixas_minuto (
    data_tv DATE, emissora VARCHAR, minuto INTEGER,
    rat_abs DOUBLE, rat DOUBLE, shr DOUBLE, base VARCHAR, base_rank INTEGER, arquivo VARCHAR);
CREATE TABLE IF NOT EXISTS perfil (
    data_tv DATE, emissora VARCHAR, programa VARCHAR, hora_ini VARCHAR, hora_fim VARCHAR,
    min_ini INTEGER, min_fim INTEGER, dimensao VARCHAR, publico VARCHAR, rat_abs DOUBLE,
    base VARCHAR, base_rank INTEGER, arquivo VARCHAR);
CREATE TABLE IF NOT EXISTS programas_dia (
    data_tv DATE, programa VARCHAR, rat DOUBLE, shr DOUBLE,
    fonte VARCHAR, base_rank INTEGER, arquivo VARCHAR);
CREATE TABLE IF NOT EXISTS log_ingestao (
    quando TIMESTAMP, arquivo VARCHAR, hash VARCHAR, tipo VARCHAR, base VARCHAR,
    data_min DATE, data_max DATE, dias_gravados INTEGER, dias_ignorados INTEGER, status VARCHAR);
"""

ORDEM_TIPOS = ["historica", "faixas", "exibicoes", "perfil", "ocorrencias"]
COLUNAS = {
    "exibicoes": ["data_tv", "emissora", "programa", "seq", "hora_ini", "hora_fim", "min_ini", "min_fim",
                  "rat_abs", "rat", "shr", "base", "base_rank", "arquivo"],
    "faixas_minuto": ["data_tv", "emissora", "minuto", "rat_abs", "rat", "shr", "base", "base_rank", "arquivo"],
    "perfil": ["data_tv", "emissora", "programa", "hora_ini", "hora_fim", "min_ini", "min_fim", "dimensao",
               "publico", "rat_abs", "base", "base_rank", "arquivo"],
    "programas_dia": ["data_tv", "programa", "rat", "shr", "fonte", "base_rank", "arquivo"],
}
TABELA_DO_TIPO = {"exibicoes": "exibicoes", "faixas": "faixas_minuto", "perfil": "perfil", "historica": "programas_dia"}


def conectar(caminho: Path = config.BASE, somente_leitura: bool = False) -> duckdb.DuckDBPyConnection:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(caminho), read_only=somente_leitura)
    if not somente_leitura:
        con.execute(ESQUEMA)
    return con


def hash_arquivo(caminho: Path) -> str:
    h = hashlib.sha1()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def ja_processado(con, hash_: str) -> bool:
    return con.execute("SELECT count(*) FROM log_ingestao WHERE hash = ? AND status = 'ok'", [hash_]).fetchone()[0] > 0


def upsert_por_dia(con, tabela: str, df: pd.DataFrame, rank: int) -> tuple[list, list]:
    """Substitui as datas do lote quando a prioridade nova >= existente. Devolve (gravadas, ignoradas)."""
    if df.empty:
        return [], []
    df = df[COLUNAS[tabela]].copy()
    df["data_tv"] = pd.to_datetime(df["data_tv"]).dt.date  # chaves sempre como date
    con.register("novo", df)
    existentes = {pd.Timestamp(d).date(): r for d, r in con.execute(
        f"SELECT data_tv, max(base_rank) FROM {tabela} WHERE data_tv IN (SELECT DISTINCT data_tv FROM novo) GROUP BY 1"
    ).fetchall()}
    dias = sorted(df["data_tv"].unique())
    gravar = [d for d in dias if existentes.get(d, -1) <= rank]
    ignorar = [d for d in dias if d not in gravar]
    if gravar:
        con.register("dias", pd.DataFrame({"data_tv": gravar}))
        con.execute(f"DELETE FROM {tabela} WHERE data_tv IN (SELECT data_tv FROM dias)")
        con.execute(f"INSERT INTO {tabela} SELECT * FROM novo WHERE data_tv IN (SELECT data_tv FROM dias)")
        con.unregister("dias")
    con.unregister("novo")
    return gravar, ignorar


def substituir_tabela(con, tabela: str, df: pd.DataFrame) -> None:
    con.register("novo", df)
    con.execute(f"CREATE OR REPLACE TABLE {tabela} AS SELECT * FROM novo")
    con.unregister("novo")


def derivar_programas_dia(con, dias: list) -> list:
    """Cria linhas no padrão BASE_HISTORICA para dias sem referência.

    Com minuto a minuto do dia: Rat% = média dos minutos do programa e
    Shr% [Total Ligados Especial] = média de Rat% / média de TLE (TLE = Rat% / Shr% do minuto).
    Sem minuto a minuto: média das exibições ponderada pela duração (Rat% e Shr%).
    A fonte (live/consolidado) segue a base do dado que foi usado.
    """
    if not dias:
        return []
    con.register("dias", pd.DataFrame({"data_tv": sorted(set(dias))}))
    novos = con.execute(f"""
        WITH e AS (
            SELECT data_tv, programa, min_ini, min_fim, greatest(min_fim - min_ini, 1) AS dur,
                   rat, shr, base_rank
            FROM exibicoes
            WHERE emissora = '{config.EMISSORA_PROPRIA}' AND data_tv IN (SELECT data_tv FROM dias)),
        pond AS (
            SELECT data_tv, programa, sum(rat * dur) / sum(dur) AS rat, sum(shr * dur) / sum(dur) AS shr_exib,
                   min(base_rank) AS base_rank
            FROM e GROUP BY 1, 2),
        minutos AS (
            SELECT e.data_tv, e.programa, avg(f.rat) AS rat_min,
                   avg(f.rat) / avg(f.rat / nullif(f.shr, 0) * 100) * 100 AS shr_tle,
                   min(f.base_rank) AS rank_min
            FROM e JOIN faixas_minuto f
              ON f.data_tv = e.data_tv AND f.emissora = '{config.EMISSORA_PROPRIA}'
             AND f.minuto >= e.min_ini AND f.minuto < e.min_fim
            GROUP BY 1, 2)
        SELECT p.data_tv, p.programa, round(coalesce(m.rat_min, p.rat), 2) AS rat,
               round(coalesce(m.shr_tle, p.shr_exib), 2) AS shr,
               CASE WHEN coalesce(m.rank_min, p.base_rank) >= 2
                    THEN 'derivado_consolidado' ELSE 'derivado_live' END AS fonte
        FROM pond p LEFT JOIN minutos m USING (data_tv, programa)
    """).df()
    con.unregister("dias")
    if novos.empty:
        return []
    # a data inteira assume a pior fonte entre seus programas (o upsert é por dia)
    novos["base_rank"] = novos["fonte"].map(config.RANK_FONTE)
    novos["base_rank"] = novos.groupby("data_tv")["base_rank"].transform("min")
    inv = {v: k for k, v in config.RANK_FONTE.items()}
    novos["fonte"] = novos["base_rank"].map(inv)
    novos["arquivo"] = "derivado"
    gravados = []
    for rank, parte in novos.groupby("base_rank"):
        g, _ = upsert_por_dia(con, "programas_dia", parte, int(rank))
        gravados += g
    return gravados


def _registrar(con, caminho: Path, hash_: str, lote, gravados, ignorados, status: str):
    tipo = getattr(lote, "tipo", None)
    base = getattr(lote, "base", None)
    datas = None
    if isinstance(lote, Lote):
        col = "data_tv" if "data_tv" in lote.df.columns else "data"
        datas = pd.to_datetime(lote.df[col])
    con.execute("INSERT INTO log_ingestao VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        datetime.now(), caminho.name, hash_, tipo, base,
        None if datas is None else datas.min().date(), None if datas is None else datas.max().date(),
        len(gravados), len(ignorados), status])


def processar(arquivos: list[Path], con=None, forcar: bool = False, saida=print) -> dict:
    """Lê os arquivos, aplica na ordem certa e deriva programas_dia. Devolve um resumo."""
    proprio = con is None
    con = con or conectar()
    resumo = {"arquivos": [], "dias_novos": set(), "dias_derivados": [], "ignorados": []}
    lidos = []
    for caminho in sorted(map(Path, arquivos), key=lambda p: p.stat().st_mtime):
        h = hash_arquivo(caminho)
        if not forcar and ja_processado(con, h):
            saida(f"  = {caminho.name}: já processado antes (mesmo conteúdo), pulando")
            resumo["ignorados"].append((caminho.name, "já processado"))
            continue
        saida(f"  > lendo {caminho.name} ...")
        for lote in ler_arquivo(caminho):
            if isinstance(lote, Ignorado):
                saida(f"  - {caminho.name}: ignorado ({lote.motivo})")
                resumo["ignorados"].append((caminho.name, lote.motivo))
                _registrar(con, caminho, h, lote, [], [], f"ignorado: {lote.motivo}")
            else:
                lidos.append((caminho, h, lote))

    lidos.sort(key=lambda t: ORDEM_TIPOS.index(t[2].tipo))
    tocados = set()
    for caminho, h, lote in lidos:
        df = lote.df.copy()
        if lote.tipo == "ocorrencias":
            substituir_tabela(con, lote.tipo, df)
            gravados, ignorados = list(df.iloc[:, 0].unique()), []
        else:
            tabela = TABELA_DO_TIPO[lote.tipo]
            if lote.tipo == "historica":
                df["fonte"], rank = "referencia", config.RANK_FONTE["referencia"]
            else:
                df["base"], rank = lote.base, config.RANK_BASE[lote.base]
            df["base_rank"], df["arquivo"] = rank, caminho.name
            gravados, ignorados = upsert_por_dia(con, tabela, df, rank)
            if lote.tipo in ("exibicoes", "faixas"):
                tocados.update(gravados)
            resumo["dias_novos"].update(gravados)
        _registrar(con, caminho, h, lote, gravados, ignorados, "ok")
        saida(f"  ✓ {caminho.name} [{lote.tipo}, {lote.base}]: {len(gravados)} dia(s) gravado(s)"
              + (f", {len(ignorados)} mantido(s) por já ter base melhor" if ignorados else ""))
        resumo["arquivos"].append((caminho.name, lote.tipo, lote.base, len(gravados), len(ignorados)))

    resumo["dias_derivados"] = derivar_programas_dia(con, sorted(tocados))
    if resumo["dias_derivados"]:
        saida(f"  ✓ programas_dia: {len(resumo['dias_derivados'])} dia(s) derivados do Instar")
    con.execute("CHECKPOINT")
    if proprio:
        con.close()
    return resumo


def status_base(con) -> pd.DataFrame:
    linhas = []
    for tabela, col in [("programas_dia", "data_tv"), ("exibicoes", "data_tv"), ("faixas_minuto", "data_tv"),
                        ("perfil", "data_tv"), ("ocorrencias", "data")]:
        try:
            mn, mx, n = con.execute(f"SELECT min({col}), max({col}), count(*) FROM {tabela}").fetchone()
        except duckdb.CatalogException:
            mn = mx = n = None
        linhas.append({"tabela": tabela, "de": mn, "até": mx, "linhas": n})
    return pd.DataFrame(linhas)


def dias_so_live(con) -> list:
    return [r[0] for r in con.execute(
        "SELECT data_tv FROM exibicoes GROUP BY 1 HAVING max(base_rank) < 2 "
        "AND data_tv >= current_date - INTERVAL 30 DAY ORDER BY 1").fetchall()]
