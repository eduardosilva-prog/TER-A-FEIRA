from datetime import date

import pandas as pd
import pytest

import config
from analise import metricas
from tests.conftest import arquivo


@pytest.fixture(scope="module")
def historica():
    h = pd.read_excel(arquivo("BASE_HISTORICA_V1_RF.xlsx"), engine="calamine")
    h.columns = ["data_tv", "programa", "rat", "shr"]
    h["data_tv"] = pd.to_datetime(h["data_tv"], format="%d/%m/%Y").dt.date
    return h


def test_semanal_reproduz_base_semanal(historica):
    """Réplica da BASE_SEMANAL para os programas locais em 20 semanas (2019 e 2026 incluídos)."""
    orig = pd.read_excel(arquivo("BASE_SEMANAL_V1_RF.xlsx"), engine="calamine")
    nova = metricas.semanal_formato_referencia(historica[historica["data_tv"] <= date(2026, 9, 27)])
    locais = set(pd.read_csv(config.PRODUTOS_CSV)["programa"])
    semanas = sorted(orig["Semana"].unique(), key=lambda s: pd.to_datetime(s, dayfirst=True))
    amostra = semanas[::len(semanas) // 18][:18] + ["04/11/2019", "21/09/2026"]
    o = orig[orig["Semana"].isin(amostra) & orig["Nome Programa"].isin(locais)]
    m = o.merge(nova, on=["Semana", "Nome Programa"], suffixes=("_o", "_n"))
    assert len(m) == len(o) and len(m) > 50
    assert (m["Rat%_o"] - m["Rat%_n"]).abs().max() <= 0.01
    assert (m["Shr%_o"] - m["Shr%_n"]).abs().max() <= 0.01
    assert (m["Exibições_o"] == m["Exibições_n"]).all()
    assert (m["Comparável_o"] == m["Comparável_n"]).all()


def _linha(**kw):
    base = {"rat": 10.0, "comparavel": True, "exibicoes": 5, "exib_habituais": 5, "d_pt_media": 0.0, "d_pct_media": 0.0}
    base.update(kw)
    return base


@pytest.mark.parametrize("kw, marca, esperado", [
    ({"d_pt_media": -1.2, "d_pct_media": -12.0}, None, "Reforçar"),
    ({"d_pt_media": 1.2, "d_pct_media": 12.0}, None, "Aproveitar"),
    ({"d_pt_media": -0.3, "d_pct_media": -12.0}, None, "Estável"),   # % alto mas poucos pontos
    ({"d_pt_media": -0.8, "d_pct_media": -4.0}, None, "Estável"),    # pontos altos mas % baixo
    ({"comparavel": False, "exibicoes": 2}, None, "Atípico"),
    ({"d_pt_media": -2.0, "d_pct_media": -20.0}, "evento: 12/10 feriado", "Atípico"),
    ({"rat": None}, None, "Sem exibição"),
])
def test_classificacao(kw, marca, esperado):
    classe, _ = metricas._classificar(_linha(**kw), 10.0, 0.5, marca)
    assert classe == esperado
