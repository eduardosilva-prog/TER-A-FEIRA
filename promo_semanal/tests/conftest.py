import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import config  # noqa: E402

ORIGEM = config.PASTA_ORIGEM


def arquivo(nome: str) -> Path:
    p = ORIGEM / nome
    if not p.exists():
        pytest.skip(f"{nome} não está na pasta de origem")
    return p


@pytest.fixture
def con(tmp_path):
    from ingestao.base import conectar
    c = conectar(tmp_path / "teste.duckdb")
    yield c
    c.close()
