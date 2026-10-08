"""Rotina diária: ingere o que estiver em entrada/, atualiza as bases de referência e arquiva.

Uso (VS Code: Ctrl+Shift+B → "Atualizar base EPTV"):
    python ingestao/atualizar.py [--sem-referencias] [--forcar]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb

import config
from ingestao.base import conectar, dias_so_live, processar, status_base
from ingestao.exportar_referencias import exportar

EXTENSOES = {".xlsx", ".xlsm", ".csv"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-referencias", action="store_true", help="não regrava BASE_HISTORICA/BASE_SEMANAL")
    ap.add_argument("--forcar", action="store_true", help="reprocessa arquivos já vistos")
    args = ap.parse_args()

    config.ENTRADA.mkdir(parents=True, exist_ok=True)
    arquivos = [p for p in config.ENTRADA.iterdir()
                if p.is_file() and p.suffix.lower() in EXTENSOES and not p.name.startswith("~$")]
    if not arquivos:
        print(f"Nada em {config.ENTRADA}. Solte ali os downloads do Instar e rode de novo.")
        return 0

    print(f"Atualizando a base com {len(arquivos)} arquivo(s) de entrada/")
    try:
        con = conectar()
    except duckdb.IOException:
        print("A base está aberta em outro processo. Feche o painel (Ctrl+C no terminal do Streamlit) e rode de novo.")
        return 1
    resumo = processar(arquivos, con=con, forcar=args.forcar)

    destino = config.PROCESSADOS / date.today().isoformat()
    destino.mkdir(parents=True, exist_ok=True)
    for p in arquivos:
        shutil.move(str(p), destino / p.name)
    print(f"  ✓ {len(arquivos)} arquivo(s) movido(s) para {destino.relative_to(config.RAIZ)}")

    if resumo["dias_novos"] and not args.sem_referencias:
        exportar(con)

    print()
    print(status_base(con).to_string(index=False))
    live = dias_so_live(con)
    if live:
        print("Dias ainda só em Live (aguardando Consolidado): " + ", ".join(f"{d:%d/%m}" for d in live))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
