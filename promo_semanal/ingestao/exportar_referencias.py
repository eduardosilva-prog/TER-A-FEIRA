"""Regrava BASE_HISTORICA_V1_RF.xlsx e BASE_SEMANAL_V1_RF.xlsx a partir da base única.

Mantém o layout original (aba Crosstab / Semanal, datas dd/mm/aaaa) e salva backup antes.
Uso: python ingestao/exportar_referencias.py
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config
from analise.metricas import semanal_formato_referencia
from ingestao.base import conectar


def _backup(arquivos: list[Path]) -> Path:
    destino = config.BACKUP / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    destino.mkdir(parents=True, exist_ok=True)
    for a in arquivos:
        if a.exists():
            shutil.copy2(a, destino / a.name)
    antigos = sorted(p for p in config.BACKUP.iterdir() if p.is_dir())
    for velho in antigos[: -config.BACKUPS_MANTIDOS]:
        shutil.rmtree(velho, ignore_errors=True)
    return destino


def _gravar(df: pd.DataFrame, caminho: Path, aba: str) -> None:
    tmp = caminho.with_name(f"~tmp_{caminho.name}")
    with pd.ExcelWriter(tmp, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=aba, index=False)
    tmp.replace(caminho)


def exportar(con=None, saida=print) -> None:
    proprio = con is None
    con = con or conectar(somente_leitura=True)
    pdia = con.execute("SELECT data_tv, programa, rat, shr FROM programas_dia ORDER BY data_tv, programa").df()
    if proprio:
        con.close()
    pdia["data_tv"] = pd.to_datetime(pdia["data_tv"]).dt.date

    historica = pd.DataFrame({
        "Data": pd.to_datetime(pdia["data_tv"]).dt.strftime("%d/%m/%Y"),
        "Nome Programa": pdia["programa"],
        "Rat%": pdia["rat"],
        "Shr% [Total Ligados Especial]": pdia["shr"],
    })
    semanal = semanal_formato_referencia(pdia)

    pasta = _backup([config.REF_HISTORICA, config.REF_SEMANAL])
    saida(f"  ✓ backup das bases de referência em backup/{pasta.name}")
    _gravar(historica, config.REF_HISTORICA, "Crosstab")
    saida(f"  ✓ {config.REF_HISTORICA.name}: {len(historica):,} linhas até {pdia['data_tv'].max():%d/%m/%Y}")
    _gravar(semanal, config.REF_SEMANAL, "Semanal")
    saida(f"  ✓ {config.REF_SEMANAL.name}: {len(semanal):,} linhas, última semana {semanal['Semana'].iloc[-1]}")


if __name__ == "__main__":
    exportar()
