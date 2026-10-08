import shutil
from datetime import date

import pandas as pd
import pytest

import config
from analise.semana_tv import hora_para_minuto, minuto_para_hora, rotulo_semana, ultima_semana_completa
from ingestao.base import processar, upsert_por_dia
from ingestao.leitores import Ignorado, ler_arquivo
from tests.conftest import arquivo


def test_dia_tv():
    assert hora_para_minuto("06:00:00") == 0
    assert hora_para_minuto("25:30:00") == 1170  # madrugada pertence ao dia de TV anterior
    assert hora_para_minuto("29:59:00") == 1439
    assert minuto_para_hora(1170) == "25:30"


def test_semana_tv():
    assert rotulo_semana(date(2026, 9, 28)) == "S40 · 28/09–04/10/2026"
    assert ultima_semana_completa(date(2026, 10, 7)) == date(2026, 9, 28)
    assert ultima_semana_completa(date(2026, 10, 4)) == date(2026, 9, 28)  # domingo fecha a semana


@pytest.mark.parametrize("nome, tipos, base", [
    ("INGESTAO DIARIA PROGRAMAS (3).xlsx", ["exibicoes"], "Live"),
    ("INGESTAO DIARIA FAIXAS (1).xlsx", ["faixas"], "Consolidado"),
    ("PERFIL_TEMP.xlsx", ["perfil"], "Consolidado"),
    ("agente_cronologia/seed/Ocorrencias_2024_2026.csv", ["ocorrencias"], None),
])
def test_deteccao_de_tipo(nome, tipos, base):
    lotes = ler_arquivo(arquivo(nome))
    assert [l.tipo for l in lotes] == tipos
    if base:
        assert lotes[0].base == base


def test_semanal_e_ignorada():
    lotes = ler_arquivo(arquivo("BASE_SEMANAL_V1_RF.xlsx"))
    assert isinstance(lotes[0], Ignorado)


def test_perfil_em_formato_longo():
    df = ler_arquivo(arquivo("PERFIL_TEMP.xlsx"))[0].df
    assert set(df["dimensao"]) == {"Classe", "Idade", "Sexo"}
    assert {"GLOBO", "RECORD", "SBT", "TV BAND"} <= set(df["emissora"])


def _exib(dia, rat, base_rank):
    return pd.DataFrame([{"data_tv": dia, "emissora": "GLOBO", "programa": "X", "seq": 0, "hora_ini": "06:00:00",
                          "hora_fim": "07:00:00", "min_ini": 0, "min_fim": 60, "rat_abs": 1.0, "rat": rat, "shr": 10.0,
                          "base": "?", "base_rank": base_rank, "arquivo": "t"}])


def test_consolidado_substitui_live_e_nao_o_contrario(con):
    d = date(2026, 10, 6)
    upsert_por_dia(con, "exibicoes", _exib(d, 5.0, 1), 1)          # Live
    gravados, _ = upsert_por_dia(con, "exibicoes", _exib(d, 6.0, 2), 2)  # Consolidado
    assert gravados == [d]
    _, ignorados = upsert_por_dia(con, "exibicoes", _exib(d, 7.0, 1), 1)  # Live atrasado
    assert ignorados == [d]
    assert con.execute("SELECT rat FROM exibicoes").fetchall() == [(6.0,)]


def test_reprocessar_mesmo_arquivo_nao_duplica(con):
    f = arquivo("INGESTAO DIARIA PROGRAMAS (3).xlsx")
    processar([f], con=con, saida=lambda *_: None)
    n = con.execute("SELECT count(*) FROM exibicoes").fetchone()[0]
    r = processar([f], con=con, saida=lambda *_: None)
    assert r["ignorados"] and con.execute("SELECT count(*) FROM exibicoes").fetchone()[0] == n
    processar([f], con=con, forcar=True, saida=lambda *_: None)  # forçado: substitui o dia, sem duplicar
    assert con.execute("SELECT count(*) FROM exibicoes").fetchone()[0] == n


def test_derivacao_bate_com_base_historica(con):
    processar([arquivo("INGESTAO DIARIA PROGRAMAS (3).xlsx"), arquivo("INGESTAO DIARIA FAIXAS (2).xlsx")],
              con=con, saida=lambda *_: None)
    der = con.execute("SELECT programa, rat, shr, fonte FROM programas_dia WHERE data_tv = '2026-10-06'").df()
    # horários vêm do PROGRAMAS (Live), valores do minuto a minuto (Consolidado)
    assert set(der["fonte"]) == {"derivado_consolidado"}
    ref = pd.read_excel(arquivo("BASE_HISTORICA_V1_RF.xlsx"), engine="calamine")
    ref.columns = ["data", "programa", "rat", "shr"]
    ref = ref[ref["data"] == "06/10/2026"]
    m = der.merge(ref, on="programa", suffixes=("_d", "_r"))
    assert len(m) >= 20
    assert (m["rat_d"] - m["rat_r"]).abs().quantile(0.9) <= 0.02
    assert (m["rat_d"] - m["rat_r"]).abs().max() <= 0.1
    assert (m["shr_d"] - m["shr_r"]).abs().max() <= 0.5


def test_referencia_nao_e_sobrescrita_por_derivado(con):
    processar([arquivo("BASE_HISTORICA_V1_RF.xlsx")], con=con, saida=lambda *_: None)
    processar([arquivo("INGESTAO DIARIA PROGRAMAS (3).xlsx"), arquivo("INGESTAO DIARIA FAIXAS (2).xlsx")],
              con=con, saida=lambda *_: None)
    fontes = con.execute("SELECT DISTINCT fonte FROM programas_dia WHERE data_tv = '2026-10-06'").fetchall()
    assert fontes == [("referencia",)]


def test_exportar_referencias_em_pasta_temporaria(con, tmp_path, monkeypatch):
    from ingestao import exportar_referencias
    processar([arquivo("INGESTAO DIARIA PROGRAMAS (3).xlsx"), arquivo("INGESTAO DIARIA FAIXAS (2).xlsx")],
              con=con, saida=lambda *_: None)
    monkeypatch.setattr(config, "REF_HISTORICA", tmp_path / "H.xlsx")
    monkeypatch.setattr(config, "REF_SEMANAL", tmp_path / "S.xlsx")
    monkeypatch.setattr(config, "BACKUP", tmp_path / "bk")
    shutil.copy(arquivo("BASE_SEMANAL_V1_RF.xlsx"), tmp_path / "S.xlsx")
    exportar_referencias.exportar(con, saida=lambda *_: None)
    h = pd.read_excel(tmp_path / "H.xlsx", engine="calamine")
    assert list(h.columns) == ["Data", "Nome Programa", "Rat%", "Shr% [Total Ligados Especial]"]
    assert (h["Data"] == "06/10/2026").sum() >= 20
    s = pd.read_excel(tmp_path / "S.xlsx", engine="calamine")
    assert list(s.columns) == ["Semana", "Fim semana", "Nome Programa", "Rat%", "Shr%", "Exibições",
                               "Exib habituais", "Dias base", "Completa", "Comparável"]
    assert any((tmp_path / "bk").iterdir())  # backup criado antes de regravar
