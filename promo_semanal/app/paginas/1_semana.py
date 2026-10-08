from datetime import timedelta

import streamlit as st

import comum
from analise import eventos
from analise.semana_tv import rotulo_semana

b, v = comum.base()
e = comum.estado()
seg = e["semana"]

st.title(f"Semana {rotulo_semana(seg)}")
st.caption("Produtos locais · Globo/EPTV · Total Domicílios · Grande Campinas. "
           f"Comparativos: semana anterior, média das {e['n_media']} semanas comparáveis anteriores e mesma semana do ano anterior.")
comum.aviso_previa(v, seg)

comp = comum.calc_comparativos(b, seg, e)

# ---------------------------------------------------------------- cards
for linha in range(0, len(comp), 4):
    cols = st.columns(4)
    for col, (_, r) in zip(cols, comp.iloc[linha:linha + 4].iterrows()):
        with col.container(border=True):
            st.markdown(f"**{r['produto']}**  \n{comum.selo_classe(r['classe'])}")
            if r["rat"] is None or r["rat"] != r["rat"]:
                st.caption(r["motivo"])
                continue
            st.metric("Rat%", comum.br(r["rat"]),
                      delta=None if r["d_pt_media"] is None else f"{comum.br(r['d_pt_media'], 2, True)} pt vs média",
                      border=False)
            st.caption(
                f"Shr% {comum.br(r['shr'], 1)} · Rat# {comum.br(r['rat_abs'], 1)} mil  \n"
                f"vs sem. anterior **{comum.br(r['d_pct_ant'], 1, True, '%')}** · "
                f"vs ano anterior **{comum.br(r['d_pct_ano'], 1, True, '%')}**  \n"
                f"{int(r['exibicoes'])} de {int(r['exib_habituais'])} exibições · {r['motivo']}")

# ---------------------------------------------------------------- tabela
st.subheader("Quadro da semana")
tabela = comp[["produto", "classe", "rat", "shr", "rat_abs", "d_pct_ant", "d_pct_media", "d_pct_ano",
               "exibicoes", "exib_habituais", "serie", "motivo"]].copy()
tabela["classe"] = tabela["classe"].map(lambda c: f"{comum.CLASSE_ESTILO[c][1]} {c}")
fmt = {"rat": (2,), "shr": (1,), "rat_abs": (1,), "d_pct_ant": (1, True, "%"), "d_pct_media": (1, True, "%"),
       "d_pct_ano": (1, True, "%"), "exibicoes": (0,), "exib_habituais": (0,)}
st.dataframe(comum.formatar(tabela, fmt), hide_index=True, width="stretch", column_config={
    "produto": "Produto", "classe": "Direcionamento", "rat": "Rat%", "shr": "Shr%", "rat_abs": "Rat# (mil)",
    "d_pct_ant": "Δ% sem. ant.", "d_pct_media": f"Δ% média {e['n_media']} sem.", "d_pct_ano": "Δ% ano ant.",
    "exibicoes": "Exib.", "exib_habituais": "Habituais",
    "serie": st.column_config.LineChartColumn("Rat% · 12 semanas"),
    "motivo": "Motivo",
})

# ---------------------------------------------------------------- produtos diários
st.subheader("Dia a dia dos produtos diários")
diarios = [p for p in b["ordem"] if len(comum.metricas.dias_habituais(b["pdd"], p, seg + timedelta(days=7))) >= 4][:4]
if diarios:
    st.plotly_chart(comum.fig_diario(comum.calc_diario_semana(b, seg), diarios), width="stretch")

# ---------------------------------------------------------------- eventos
st.subheader("O que aconteceu na semana")
ev = eventos.eventos_semana(b["ev"], seg)
if ev.empty:
    st.caption("Nenhum evento relevante registrado.")
else:
    ev = ev.assign(dia=lambda d: d["data"].map(lambda x: f"{comum.DIAS_PT[x.weekday()]} {x:%d/%m}"))
    st.dataframe(ev[["dia", "icone", "categoria", "titulo", "horario", "grupo"]], hide_index=True, width="stretch",
                 column_config={"dia": "Dia", "icone": " ", "categoria": "Tipo", "titulo": "Evento",
                                "horario": "Hora", "grupo": "Destaque"})
