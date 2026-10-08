"""Caminhos e parâmetros do projeto."""
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PASTA_ORIGEM = RAIZ.parent  # TERÇA-FEIRAS: onde ficam as bases de referência
ENTRADA = RAIZ / "entrada"
PROCESSADOS = ENTRADA / "processados"
BACKUP = RAIZ / "backup"
BASE = RAIZ / "base" / "eptv_promo.duckdb"
PRODUTOS_CSV = RAIZ / "config" / "produtos.csv"
TIMES_CSV = RAIZ / "config" / "times_regiao.csv"

# Bases de referência regravadas a cada atualização
REF_HISTORICA = PASTA_ORIGEM / "BASE_HISTORICA_V1_RF.xlsx"
REF_SEMANAL = PASTA_ORIGEM / "BASE_SEMANAL_V1_RF.xlsx"
BACKUPS_MANTIDOS = 10

EMISSORA_PROPRIA = "GLOBO"

# O painel só considera dados a partir desta data (a base única e as bases de
# referência regravadas continuam com o histórico completo).
DATA_INICIO_ANALISE = date(2024, 1, 1)

# Prioridade de base: Consolidado substitui Live na mesma data
RANK_BASE = {"Consolidado": 2, "Live": 1, "Desconhecida": 0}
# Prioridade de fonte em programas_dia (equivalente à BASE_HISTORICA)
RANK_FONTE = {"referencia": 3, "derivado_consolidado": 2, "derivado_live": 1}

# Regras da BASE_SEMANAL
LIMIAR_COMPARAVEL = 0.6  # exibições >= 60% das habituais
