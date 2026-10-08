"""Monta a base única a partir dos arquivos que já estão na pasta TERÇA-FEIRAS.

Roda uma vez (ou para reconstruir do zero). Leva ~2 min por causa do minuto a minuto de 98 MB.
Uso: python ingestao/carga_inicial.py [--pasta CAMINHO] [--recriar]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from ingestao.base import conectar, processar, status_base

PADROES = ["BASE_HISTORICA*.xlsx", "INGESTAO DIARIA*.xlsx", "PERFIL*.xlsx"]
# Ocorrências vêm do agente de cronologia (export filtrado); o seed é o plano B
OCORRENCIAS = [config.PASTA_ORIGEM / "agente_cronologia" / "exports" / "ocorrencias.csv",
               config.PASTA_ORIGEM / "agente_cronologia" / "seed" / "Ocorrencias_2024_2026.csv"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", type=Path, default=config.PASTA_ORIGEM)
    ap.add_argument("--recriar", action="store_true", help="apaga a base antes de carregar")
    args = ap.parse_args()

    if args.recriar and config.BASE.exists():
        config.BASE.unlink()
        print(f"Base apagada: {config.BASE}")

    arquivos = sorted({p for padrao in PADROES for p in args.pasta.glob(padrao)})
    arquivos += [next(p for p in OCORRENCIAS if p.exists())] if any(p.exists() for p in OCORRENCIAS) else []
    print(f"Carga inicial a partir de {args.pasta} ({len(arquivos)} arquivos)")
    t = time.time()
    con = conectar()
    processar(arquivos, con=con)
    print(status_base(con).to_string(index=False))
    con.close()
    print(f"Concluído em {time.time() - t:.0f}s → {config.BASE}")


if __name__ == "__main__":
    main()
