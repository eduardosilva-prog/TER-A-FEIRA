from datetime import timedelta

import streamlit as st

import comum
from analise import perfil as perfil_mod
from analise.semana_tv import DIAS_PT_LONGO, minuto_para_hora, rotulo_semana

b, v = comum.base()
e = comum.estado()
seg = e["semana"]

st.title("Onde chamar")
st.caption("Onde estão as maiores audiências da Globo para posicionar chamadas dos produtos locais.")

c1, c2, c3 = st.columns([2, 1, 1])
produto = c1.selectbox("Produto a promover", b["ordem"], key="produto_chamada")
n_sem = c2.slider("Semanas de referência", 1, 8, 4, key="n_sem_heat")
sem_fer = c3.toggle("Excluir feriados e eventos", True, key="sem_feriado_heat")

heat = comum.calc_heat(b, v, seg, n_sem, sem_fer)
ref = seg + timedelta(days=7)
janela = comum.calc_janela_chamadas(b, heat, produto, ref)

# ---------------------------------------------------------------- heatmap
st.subheader("Semana típica da Globo · Rat% por bloco de 15 min")
st.caption(f"Média de {n_sem} semana(s) até {rotulo_semana(seg)}. Círculos = melhores blocos para chamar **{produto}**.")
st.plotly_chart(comum.fig_heat(heat, janela), width="stretch")

# ---------------------------------------------------------------- janela do produto
dias = comum.metricas.dias_habituais(b["pdd"], produto, ref)
horas = comum.metricas.hora_tipica(b["pdd"], produto, ref)
st.subheader(f"Janela de chamadas · {produto}")
if not dias:
    st.info("O produto não foi ao ar nas últimas 8 semanas.")
else:
    st.caption("Vai ao ar: " + ", ".join(f"{DIAS_PT_LONGO[d]} {minuto_para_hora(horas[d])}" for d in dias if d in horas)
               + ". Ranking dos blocos de maior Rat% de até 3 dias antes e do próprio dia, antes do início.")
    if not janela.empty:
        st.dataframe(janela[["dia", "hora", "programa", "rat", "rat_abs", "dias_antes", "exibição"]], hide_index=True,
                     width="stretch", column_config={
                         "dia": "Dia", "hora": "Bloco", "programa": "Programa típico no bloco",
                         "rat": st.column_config.NumberColumn("Rat%", format="%.2f"),
                         "rat_abs": st.column_config.NumberColumn("Rat# (mil dom.)", format="%.1f"),
                         "dias_antes": st.column_config.NumberColumn("Dias antes", help="0 = mesmo dia, antes do início"),
                         "exibição": "Para a exibição de"})

# ---------------------------------------------------------------- público-alvo
st.subheader("Programas que mais entregam o público do produto")
ini, fim = comum.periodo_perfil(b, v, seg)
af = comum.calc_afinidade(b, v, produto, ini, fim)
if af.empty:
    st.info("Sem perfil do produto no período (o PERFIL começa em 01/08/2026).")
else:
    a1, a2, a3 = st.columns([1, 1, 2])
    dim = a1.radio("Dimensão", ["Idade", "Classe", "Sexo"], horizontal=True, key="dim_alvo")
    limiar = a2.number_input("Afinidade mínima", 80, 200, 110, 5, key="lim_af")
    padrao = perfil_mod.publicos_alvo(af, dim, limiar)
    opcoes = perfil_mod.ORDEM_PUBLICOS[dim]
    publicos = a3.multiselect("Público-alvo", opcoes, default=padrao, key=f"alvo_{produto}_{dim}_{limiar}")
    st.caption(f"Perfil de {ini:%d/%m} a {fim:%d/%m}. Afinidade = % do público no produto ÷ % na grade Globo × 100. "
               "Ficam de fora programas com menos de 3 exibições ou que não foram ao ar na última semana.")
    if publicos:
        r = comum.calc_onde_chamar(b, v, produto, publicos, ini, fim)
        if not r.empty:
            st.plotly_chart(comum.fig_onde_chamar(r, publicos), width="stretch")
