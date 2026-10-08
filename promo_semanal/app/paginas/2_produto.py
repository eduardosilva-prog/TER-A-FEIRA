from datetime import timedelta

import pandas as pd
import streamlit as st

import comum
from analise import eventos, faixas, metricas
from analise.semana_tv import rotulo_semana, segundas

b, v = comum.base()
e = comum.estado()
seg = e["semana"]
fim = seg + timedelta(days=6)

st.title("Produto em detalhe")
produto = st.selectbox("Produto", b["ordem"], key="produto_detalhe")
st.caption(rotulo_semana(seg))

# ---------------------------------------------------------------- série semanal
s = b["sem"][(b["sem"]["produto"] == produto) & (b["sem"]["semana"] <= seg)].tail(52).copy()
ano = b["sem"][b["sem"]["produto"] == produto].copy()
ano["semana_plot"] = ano["semana"] + timedelta(days=364)
ano = ano[ano["semana_plot"].isin(set(s["semana"]))]
ev = b["ev"]
marcadas = eventos.datas_marcadas(ev)
marcas = {}
for d, t in marcadas.items():
    marcas.setdefault(segundas(pd.Series([d])).iat[0], []).append(f"{d:%d/%m} {t}")
marcas = {k: "<br>".join(vs) for k, vs in marcas.items()}

st.subheader("Últimas 52 semanas")
st.caption("Marcador vazado = semana não comparável (exibições abaixo de 60% das habituais). "
           "Passe o mouse para ver feriados e acontecimentos da semana.")
if s.empty:
    st.info("Sem exibições no período.")
else:
    st.plotly_chart(comum.fig_semanal_produto(s, ano, marcas), width="stretch")

# ---------------------------------------------------------------- minuto a minuto
st.subheader("Minuto a minuto na semana")
segs = metricas.segmentos_produto(b["ex"], b["prods"], produto, seg, fim)
if segs.empty:
    st.info("Sem minuto a minuto do produto nesta semana.")
else:
    fx = comum.faixas_periodo(v, seg, fim)
    cur, ind = faixas.curva_exibicoes(fx, segs)
    if not cur.empty:
        st.plotly_chart(comum.fig_curva(cur), width="stretch")
        st.caption("Herança = abertura ÷ 5 min anteriores. Retenção = fechamento ÷ abertura (5 min cada). "
                   "Lacunas na linha = intervalos dentro do produto (ex.: horário eleitoral).")
        ind["dia"] = ind["data_tv"].map(lambda d: f"{comum.DIAS_PT[d.weekday()]} {d:%d/%m}")
        st.dataframe(ind[["dia", "inicio", "fim", "duracao", "blocos", "lead_in", "abertura", "media", "pico",
                          "hora_pico", "fechamento", "lead_out", "heranca", "retencao"]],
                     hide_index=True, width="stretch", column_config={
                         "dia": "Dia", "inicio": "Início", "fim": "Fim", "duracao": "Min no ar", "blocos": "Blocos",
                         "lead_in": st.column_config.NumberColumn("Antes (5 min)", format="%.2f"),
                         "abertura": st.column_config.NumberColumn("Abertura", format="%.2f"),
                         "media": st.column_config.NumberColumn("Média", format="%.2f"),
                         "pico": st.column_config.NumberColumn("Pico", format="%.2f"),
                         "hora_pico": "Hora do pico",
                         "fechamento": st.column_config.NumberColumn("Fechamento", format="%.2f"),
                         "lead_out": st.column_config.NumberColumn("Depois (5 min)", format="%.2f"),
                         "heranca": st.column_config.NumberColumn("Herança %", format="%.0f"),
                         "retencao": st.column_config.NumberColumn("Retenção %", format="%.0f"),
                     })

# ---------------------------------------------------------------- dia a dia vs semana anterior
st.subheader("Dia a dia contra a semana anterior")
p = b["pdd"][b["pdd"]["produto"] == produto].set_index("data_tv")
linhas = []
for i in range(7):
    d = seg + timedelta(days=i)
    a = d - timedelta(days=7)
    if d not in p.index and a not in p.index:
        continue
    r_d = p.loc[d] if d in p.index else None
    r_a = p.loc[a] if a in p.index else None
    linhas.append({
        "dia": f"{comum.DIAS_PT[i]} {d:%d/%m}", "evento": marcadas.get(d, ""),
        "rat": None if r_d is None else r_d["rat"], "shr": None if r_d is None else r_d["shr"],
        "rat_abs": None if r_d is None else r_d["rat_abs"],
        "rat_ant": None if r_a is None else r_a["rat"],
        "delta": None if r_d is None or r_a is None else (r_d["rat"] / r_a["rat"] - 1) * 100,
    })
if linhas:
    t = pd.DataFrame(linhas)
    num = ["rat", "shr", "rat_abs", "rat_ant", "delta"]
    t[num] = t[num].astype(float)  # None -> vazio na tabela
    estilo = comum.formatar(t, {"rat": (2,), "shr": (1,), "rat_abs": (1,), "rat_ant": (2,), "delta": (1, True, "%")},
                            cores=["delta"])
    st.dataframe(estilo, hide_index=True, width="stretch", column_config={
        "dia": "Dia", "evento": "Evento", "rat": "Rat%", "shr": "Shr%", "rat_abs": "Rat# (mil)",
        "rat_ant": "Rat% sem. ant.", "delta": "Δ%"})

rep = b["pdd_rep"][(b["pdd_rep"]["produto"] == produto) & (b["pdd_rep"]["data_tv"] >= seg) & (b["pdd_rep"]["data_tv"] <= fim)]
if not rep.empty:
    st.subheader("Reprises na semana")
    rep = rep.assign(dia=rep["data_tv"].map(lambda d: f"{comum.DIAS_PT[d.weekday()]} {d:%d/%m}"))
    st.dataframe(rep[["dia", "programas", "rat", "shr"]], hide_index=True, width="stretch", column_config={
        "dia": "Dia", "programas": "Programa", "rat": st.column_config.NumberColumn("Rat%", format="%.2f"),
        "shr": st.column_config.NumberColumn("Shr%", format="%.1f")})
