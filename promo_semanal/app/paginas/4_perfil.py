from datetime import timedelta

import pandas as pd
import streamlit as st

import comum
from analise import metricas, perfil as perfil_mod
from analise.semana_tv import rotulo_semana

b, v = comum.base()
e = comum.estado()
seg = e["semana"]
fim_sem = seg + timedelta(days=6)

st.title("Perfil e concorrência")
produto = st.selectbox("Produto", b["ordem"], key="produto_perfil")

p = comum.perfil_todo(v)
st.caption(f"PERFIL disponível de {p['data_tv'].min():%d/%m/%Y} a {p['data_tv'].max():%d/%m/%Y} "
           "(Rat# em mil indivíduos, Consolidado). O histórico cresce a cada dia ingerido.")

ini8, fim8 = comum.periodo_perfil(b, v, seg)
af_sem = comum.calc_afinidade(b, v, produto, seg, fim_sem)
af_8 = comum.calc_afinidade(b, v, produto, ini8, fim8)

if af_8.empty:
    st.info("Sem perfil do produto no período.")
    st.stop()

# ---------------------------------------------------------------- composição
st.subheader("Composição do público")
series = []
if not af_sem.empty:
    series.append(af_sem.assign(serie=f"{produto} · {rotulo_semana(seg)}"))
series.append(af_8.assign(serie=f"{produto} · {ini8:%d/%m}–{fim8:%d/%m}"))
series.append(af_8.assign(pct=af_8["pct_globo"], serie="Grade Globo (mesmo período)"))
comp = pd.concat(series)
abas = st.tabs(["Idade", "Classe", "Sexo"])
for aba, dim in zip(abas, ["Idade", "Classe", "Sexo"]):
    with aba:
        st.plotly_chart(comum.fig_perfil(comp, dim), width="stretch")

# ---------------------------------------------------------------- afinidade
st.subheader("Afinidade com a grade Globo")
base_af = af_sem if not af_sem.empty else af_8
t = base_af[["dimensao", "publico", "pct", "pct_globo", "afinidade"]].copy()
t["af_delta"] = t["afinidade"] - 100
st.dataframe(t.style.map(comum.cor_delta, subset=["af_delta"]), hide_index=True, width="stretch", column_config={
    "dimensao": "Dimensão", "publico": "Público",
    "pct": st.column_config.NumberColumn("% no produto", format="%.1f"),
    "pct_globo": st.column_config.NumberColumn("% na grade", format="%.1f"),
    "afinidade": st.column_config.NumberColumn("Afinidade", format="%.0f", help="100 = igual à grade"),
    "af_delta": st.column_config.NumberColumn("Acima/abaixo da grade", format="%+.0f")})

# ---------------------------------------------------------------- concorrência
st.subheader("Concorrência no horário do produto")
segs = metricas.segmentos_produto(b["ex"], b["prods"], produto, seg, fim_sem)
if segs.empty:
    # sem exibições (ou sem a tabela de exibições) na semana: usa o horário do próprio PERFIL
    nomes = b["prods"][(b["prods"]["produto"] == produto) & (b["prods"]["tipo"] == "principal")]["programa"]
    segs = p[(p["programa"].isin(nomes)) & (p["emissora"] == "GLOBO") & (p["data_tv"] >= seg)
             & (p["data_tv"] <= fim_sem)].drop_duplicates(["data_tv", "min_ini"])
conc = perfil_mod.concorrencia(p, segs) if not segs.empty else pd.DataFrame()
if conc.empty:
    st.info("Sem perfil das emissoras no horário do produto nesta semana.")
else:
    st.caption(f"{rotulo_semana(seg)} · média por minuto em que o produto esteve no ar.")
    st.plotly_chart(comum.fig_concorrencia(conc), width="stretch")
    piv = conc.pivot_table(index=["dimensao", "publico"], columns="emissora", values="pct").reset_index()
    ordem = {pub: i for lst in perfil_mod.ORDEM_PUBLICOS.values() for i, pub in enumerate(lst)}
    piv = piv.sort_values(["dimensao", "publico"], key=lambda s: s.map(ordem) if s.name == "publico" else s)
    st.caption("Composição do público de cada emissora no mesmo horário (% dentro da dimensão).")
    st.dataframe(piv, hide_index=True, width="stretch",
                 column_config={"dimensao": "Dimensão", "publico": "Público",
                                **{c: st.column_config.NumberColumn(c, format="%.1f") for c in piv.columns[2:]}})
