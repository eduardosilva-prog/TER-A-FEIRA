from datetime import timedelta

import pandas as pd
import streamlit as st

import comum
from analise import eventos
from analise.semana_tv import DIAS_PT, DIAS_PT_LONGO, dias_da_semana, rotulo_semana

b, v = comum.base()
e = comum.estado()
prox = e["proxima"]
dias = dias_da_semana(prox)
sig = comum.siglas(b)

st.title(f"Próxima semana · {rotulo_semana(prox)}")
st.caption("Feriados, datas, acontecimentos e futebol, com o comportamento dos produtos em datas parecidas. "
           "Não há grade futura: os produtos listados são os que costumam ir ao ar em cada dia.")

todos_jogos = st.toggle("Mostrar todos os jogos de competições brasileiras (não só Seleção, região e SP)", False)
ev = eventos.eventos_semana(b["ev"], prox, so_destaque_futebol=not todos_jogos)
por_dia = comum.produtos_por_dia(b, dias, prox)

# ---------------------------------------------------------------- grade da semana
cols = st.columns(7)
for col, d in zip(cols, dias):
    with col.container(border=True):
        st.markdown(f"**{DIAS_PT_LONGO[d.weekday()]}**  \n{d:%d/%m}")
        do_dia = ev[ev["data"] == d]
        for _, r in do_dia[do_dia["categoria"] != "Futebol"].iterrows():
            st.markdown(f"{r['icone']} {r['titulo']}")
        jogos = do_dia[do_dia["categoria"] == "Futebol"]
        if not jogos.empty:
            st.caption(f"⚽ {len(jogos)} jogo(s)")
        st.caption(" · ".join(sig[p] for p in por_dia[d]) or "sem produto local")

st.caption("🟥 feriado · 🟧 ponto facultativo · 🟦 data comemorativa · 🟪 acontecimento · ⚽ futebol. "
           "Siglas: " + ", ".join(f"{s} = {p}" for p, s in sig.items()))

# ---------------------------------------------------------------- futebol
jogos = ev[ev["categoria"] == "Futebol"].copy()
if not jogos.empty:
    st.subheader("Futebol na semana")
    jogos["dia"] = jogos["data"].map(lambda d: f"{DIAS_PT[d.weekday()]} {d:%d/%m}")
    st.dataframe(jogos[["dia", "horario", "titulo", "grupo", "status"]], hide_index=True, width="stretch",
                 column_config={"dia": "Dia", "horario": "Hora", "titulo": "Jogo", "grupo": "Destaque", "status": "Status"})
    st.caption("Horários conforme a fonte. As Ocorrências não indicam quais jogos a Globo transmite.")

# ---------------------------------------------------------------- análogos
st.subheader("Como os produtos se saíram em datas parecidas")
an = comum.calc_analogos(b, prox)
if an.empty:
    st.caption("Nenhum feriado, data comemorativa ou acontecimento com histórico nesta semana.")
else:
    st.caption("Δ% = Rat% do produto na data contra a média do mesmo dia da semana nas 4 semanas anteriores "
               "(sem feriados). **Não exibido** = o produto costuma ir ao ar nesse dia da semana, mas não foi.")
    for alvo, g in an.groupby("dia_alvo"):
        st.markdown(f"**{DIAS_PT_LONGO[alvo.weekday()]} {alvo:%d/%m} · {g['evento'].iat[0]}**")
        g = g.copy()
        g["valor"] = g.apply(lambda r: r["delta_pct"] if r["exibido"] else None, axis=1)
        g["data"] = g["data_analoga"].map(lambda d: f"{d:%d/%m/%Y} ({DIAS_PT[d.weekday()]})")
        piv = g.pivot_table(index="data", columns="produto", values="valor", aggfunc="first", dropna=False)
        rat = g.pivot_table(index="data", columns="produto", values="rat", aggfunc="first", dropna=False)
        nao = g[~g["exibido"]].pivot_table(index="data", columns="produto", values="dia_habitual", aggfunc="first")
        ordem_idx = g.drop_duplicates("data").sort_values("data_analoga", ascending=False)["data"]
        cols_ord = [p for p in b["ordem"] if p in piv.columns]
        piv, rat = piv.reindex(index=ordem_idx, columns=cols_ord), rat.reindex(index=ordem_idx, columns=cols_ord)
        texto = piv.copy().astype(object)
        for i in piv.index:
            for c in piv.columns:
                if pd.notna(piv.at[i, c]):
                    texto.at[i, c] = f"{comum.br(piv.at[i, c], 1, True, '%')} ({comum.br(rat.at[i, c])})"
                elif i in nao.index and c in nao.columns and pd.notna(nao.at[i, c]):
                    texto.at[i, c] = "não exibido"
                else:
                    texto.at[i, c] = ""
        estilo = texto.style.apply(lambda col: [comum.cor_delta(piv.at[i, col.name]) for i in col.index], axis=0)
        st.dataframe(estilo, width="stretch")

# ---------------------------------------------------------------- mesma semana do ano anterior
st.subheader("Mesma semana do ano anterior")
seg_ano = prox - timedelta(days=364)
comp_ano = comum.calc_comparativos(b, seg_ano, e)
ev_ano = eventos.eventos_semana(b["ev"], seg_ano)
st.caption(f"{rotulo_semana(seg_ano)}. Δ% contra a média das semanas anteriores daquele ano.")
t_ano = comp_ano[["produto", "rat", "shr", "d_pct_media", "exibicoes", "exib_habituais", "classe", "motivo"]]
st.dataframe(comum.formatar(t_ano, {"rat": (2,), "shr": (1,), "d_pct_media": (1, True, "%"), "exibicoes": (0,),
                                    "exib_habituais": (0,)}),
             hide_index=True, width="stretch", column_config={
                 "produto": "Produto", "rat": "Rat%", "shr": "Shr%", "d_pct_media": "Δ% vs média",
                 "exibicoes": "Exib.", "exib_habituais": "Habituais", "classe": "Na época", "motivo": "Motivo"})
nao_fut = ev_ano[ev_ano["categoria"] != "Futebol"]
if not nao_fut.empty:
    st.caption("Eventos daquela semana: " + "; ".join(f"{r['data']:%d/%m} {r['titulo']}" for _, r in nao_fut.iterrows()))
