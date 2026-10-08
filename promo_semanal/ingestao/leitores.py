"""Leitura dos exports do Instar e das bases de referência.

Cada arquivo vira um ou mais `Lote`s já normalizados para as tabelas da base única.
Os xlsx do Instar têm estilos que o openpyxl não lê, por isso tudo usa calamine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from analise.semana_tv import hora_para_minuto

CLASSES = ["AB1", "B2", "C1", "C2", "DE"]
SEXOS = ["HOMENS", "MULHERES"]


@dataclass
class Lote:
    tipo: str  # exibicoes | faixas | perfil | historica | ocorrencias
    df: pd.DataFrame
    base: str = "Desconhecida"
    aviso: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Ignorado:
    motivo: str


def _base_do_titulo(titulo) -> str:
    t = str(titulo)
    if "Consolidado" in t:
        return "Consolidado"
    if "Live" in t:
        return "Live"
    return "Desconhecida"


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _data(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str.strip(), format="%d/%m/%Y", errors="coerce").dt.date


def _hora(s: pd.Series) -> pd.Series:
    # calamine pode devolver texto '06:00:00' ou time; padroniza para HH:MM:SS
    return s.astype(str).str.strip().str.slice(0, 8)


def _sem_total(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df = df[df[col].astype(str).str.strip() != "Total"]
    return df.dropna(subset=[col])


def ler_exibicoes(xl: pd.ExcelFile, aba: str = "Programas") -> Lote:
    titulo = pd.read_excel(xl, sheet_name=aba, header=None, nrows=1).iloc[0, 0]
    df = pd.read_excel(xl, sheet_name=aba, header=1)
    df = _sem_total(df, "Nome Programa")
    out = pd.DataFrame({
        "data_tv": _data(df["Data"]),
        "emissora": df["Emissora"].astype(str).str.strip(),
        "programa": df["Nome Programa"].astype(str).str.strip(),
        "seq": _num(df["Sequencial"]).fillna(0).astype(int),
        "hora_ini": _hora(df["Hora Início"]),
        "hora_fim": _hora(df["Hora Fim"]),
        "rat_abs": _num(df["Rat#"]),
        "rat": _num(df["Rat%"]),
        "shr": _num(df["Shr%"]),
    })
    out["min_ini"] = out["hora_ini"].map(hora_para_minuto)
    out["min_fim"] = out["hora_fim"].map(hora_para_minuto)
    return Lote("exibicoes", out.dropna(subset=["data_tv"]), _base_do_titulo(titulo))


def ler_faixas(xl: pd.ExcelFile, aba: str = "Faixas Horárias") -> Lote:
    titulo = pd.read_excel(xl, sheet_name=aba, header=None, nrows=1).iloc[0, 0]
    df = pd.read_excel(xl, sheet_name=aba, header=1, usecols=["Data", "Hora Início", "Emissora", "Rat#", "Rat%", "Shr%"])
    df = _sem_total(df, "Data")
    out = pd.DataFrame({
        "data_tv": _data(df["Data"]),
        "emissora": df["Emissora"].astype(str).str.strip(),
        "minuto": _hora(df["Hora Início"]).map(hora_para_minuto),
        "rat_abs": _num(df["Rat#"]),
        "rat": _num(df["Rat%"]),
        "shr": _num(df["Shr%"]),
    })
    return Lote("faixas", out.dropna(subset=["data_tv"]), _base_do_titulo(titulo))


def _dimensao(publico: str) -> str:
    if publico in CLASSES:
        return "Classe"
    if publico in SEXOS:
        return "Sexo"
    if "anos" in publico:
        return "Idade"
    return "Outro"


def ler_perfil(xl: pd.ExcelFile, aba: str = "Programas") -> Lote:
    bruto = pd.read_excel(xl, sheet_name=aba, header=None)
    titulo, variaveis, cab = bruto.iloc[0, 0], bruto.iloc[1], bruto.iloc[2]
    df = bruto.iloc[3:].copy()
    df.columns = [str(c).strip() for c in cab]
    df = _sem_total(df, "Nome Programa")
    fixas = ["Nome Programa", "Emissora", "Data", "Hora Início", "Hora Fim"]
    # só as colunas de Rat# (o export pode trazer outras variáveis)
    publicos = [str(cab[i]).strip() for i in range(len(cab)) if str(variaveis[i]).strip() == "Rat#"]
    base = df[fixas].copy()
    base.columns = ["programa", "emissora", "data_tv", "hora_ini", "hora_fim"]
    base["data_tv"] = _data(base["data_tv"])
    base["hora_ini"], base["hora_fim"] = _hora(base["hora_ini"]), _hora(base["hora_fim"])
    base["programa"] = base["programa"].astype(str).str.strip()
    base["emissora"] = base["emissora"].astype(str).str.strip()
    base["min_ini"] = base["hora_ini"].map(hora_para_minuto)
    base["min_fim"] = base["hora_fim"].map(hora_para_minuto)
    valores = df[publicos].apply(_num)
    longo = pd.concat([base, valores], axis=1).melt(
        id_vars=list(base.columns), value_vars=publicos, var_name="publico", value_name="rat_abs")
    longo["dimensao"] = longo["publico"].map(_dimensao)
    return Lote("perfil", longo.dropna(subset=["data_tv"]), _base_do_titulo(titulo))


def ler_historica(xl: pd.ExcelFile, aba: str) -> Lote:
    df = pd.read_excel(xl, sheet_name=aba)
    df.columns = ["Data", "Nome Programa", "Rat%", "Shr%"][: len(df.columns)]
    out = pd.DataFrame({
        "data_tv": _data(df["Data"]),
        "programa": df["Nome Programa"].astype(str).str.strip(),
        "rat": _num(df["Rat%"]),
        "shr": _num(df["Shr%"]),
    })
    return Lote("historica", out.dropna(subset=["data_tv"]), "Referência")


def ler_csv(caminho: Path) -> Lote | Ignorado:
    df = pd.read_csv(caminho, sep=";", encoding="utf-8-sig", low_memory=False)
    cols = set(df.columns)
    if {"Tipo", "Titulo", "Competicao"} <= cols:
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.date
        df = df.rename(columns=str.lower)
        for c in ["gols_mandante", "gols_visitante"]:
            df[c] = _num(df[c])
        return Lote("ocorrencias", df.dropna(subset=["data"]))
    if {"Dia_semana", "Semana_ISO"} <= cols:
        return Ignorado("Calendário não é usado pelo painel")
    return Ignorado("CSV com colunas não reconhecidas")


def ler_arquivo(caminho: Path) -> list[Lote | Ignorado]:
    """Detecta o tipo pelo conteúdo (abas e título) e devolve os lotes normalizados."""
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".csv":
        return [ler_csv(caminho)]
    if caminho.suffix.lower() not in (".xlsx", ".xlsm", ".xls"):
        return [Ignorado(f"extensão {caminho.suffix} não suportada")]

    xl = pd.ExcelFile(caminho, engine="calamine")
    abas = xl.sheet_names
    if "Semanal" in abas:
        return [Ignorado("BASE_SEMANAL é recalculada a partir da base diária")]
    if "Leia-me" in abas and "Datas" in abas:
        return [Ignorado("Cronologia: use Ocorrencias_*.csv e Calendario_*.csv")]

    lotes: list[Lote | Ignorado] = []
    if "Faixas Horárias" in abas:
        lotes.append(ler_faixas(xl))
    if "Programas" in abas:
        linha2 = pd.read_excel(xl, sheet_name="Programas", header=None, nrows=2).iloc[1].astype(str)
        if linha2.str.contains("Variáveis").any():
            lotes.append(ler_perfil(xl))
        else:
            lotes.append(ler_exibicoes(xl))
    if not lotes:
        cab = pd.read_excel(xl, sheet_name=abas[0], nrows=0).columns.astype(str)
        if "Nome Programa" in cab and "Data" in cab and any("Rat%" in c for c in cab):
            lotes.append(ler_historica(xl, abas[0]))
    return lotes or [Ignorado(f"abas não reconhecidas: {abas}")]
