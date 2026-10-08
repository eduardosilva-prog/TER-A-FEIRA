"""Painel semanal de direcionamento para Promo · Produtos locais EPTV.

Somente leitura: a base é atualizada pelo VS Code (tarefa "Atualizar base EPTV").
Rodar: streamlit run app/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

st.set_page_config(page_title="Promo · Produtos Locais EPTV", page_icon="📺", layout="wide")

import comum  # noqa: E402

b, v = comum.base()
comum.sidebar(b)

pg = st.navigation([
    st.Page("paginas/1_semana.py", title="Semana", icon="📅", default=True),
    st.Page("paginas/2_produto.py", title="Produto em detalhe", icon="🔎"),
    st.Page("paginas/3_chamadas.py", title="Onde chamar", icon="📣"),
    st.Page("paginas/4_perfil.py", title="Perfil e concorrência", icon="👥"),
    st.Page("paginas/5_agenda.py", title="Próxima semana", icon="🗓️"),
    st.Page("paginas/6_briefing.py", title="Briefing", icon="📤"),
    st.Page("paginas/7_base.py", title="Sobre a base", icon="🗄️"),
])
pg.run()
