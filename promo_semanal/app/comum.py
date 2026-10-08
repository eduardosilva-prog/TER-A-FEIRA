"""Peças compartilhadas do painel: cache da base, estado da sidebar, paleta, cálculos e gráficos.

As páginas e o briefing usam as mesmas funções, então o que é exportado é o que aparece na tela.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import config
from analise import analogos, dados, eventos, faixas, metricas, perfil
from analise.semana_tv import (DIAS_PT, DIAS_PT_LONGO, dias_da_semana, minuto_para_hora, proxima_semana,
                               rotulo_semana, ultima_semana_completa)

# ------------------------------------------------------------------ paleta (dataviz: paleta de referência)
SERIE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
CINZA = "#898781"
CINZA_CLARO = "#c3c2b7"
SEQ_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIV = {"neg": "#d03b3b", "neg_suave": "#f2b8b5", "neutro": "#f0efec", "pos_suave": "#b7d3f6", "pos": "#2a78d6"}
CLASSE_ESTILO = {  # status sempre com ícone + rótulo
    "Reforçar": ("red", "🔻"),
    "Aproveitar": ("green", "🔺"),
    "Atípico": ("orange", "◆"),
    "Estável": ("gray", "●"),
    "Sem exibição": ("gray", "○"),
}


def br(x, casas: int = 2, sinal: bool = False, sufixo: str = "") -> str:
    if x is None or pd.isna(x):
        return "–"
    s = f"{x:+,.{casas}f}" if sinal else f"{x:,.{casas}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".") + sufixo


def formatar(df: pd.DataFrame, formatos: dict[str, tuple], cores: list[str] | None = None):
    """Tabela com números no padrão brasileiro e '–' no vazio.

    O st.dataframe mostra nulo como 'None' mesmo com Styler, então as colunas viram texto;
    as cores (escala divergente) continuam calculadas sobre os valores numéricos originais.
    formatos: coluna -> (casas, sinal, sufixo).
    """
    txt = df.copy()
    for c, f in formatos.items():
        if c in txt.columns:
            txt[c] = df[c].map(lambda x, f=f: br(x, *f))
    estilo = txt.style
    for c in cores or []:
        estilo = estilo.apply(lambda col: [cor_delta(v) for v in df[col.name]], subset=[c])
    return estilo


def selo_classe(classe: str) -> str:
    cor, icone = CLASSE_ESTILO.get(classe, ("gray", "•"))
    return f":{cor}-background[{icone} {classe}]"


def layout_padrao(fig: go.Figure, altura: int = 360, **kw) -> go.Figure:
    fig.update_layout(height=altura, margin=dict(l=8, r=8, t=36, b=8), hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), **kw)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridwidth=0.5)
    return fig


# ------------------------------------------------------------------ dados em cache

@st.cache_data(show_spinner="Carregando a base…")
def carregar(versao: float) -> dict:
    pdia = dados.programas_dia()
    ex = dados.exibicoes()
    prods = metricas.carregar_produtos()
    pdd = metricas.produtos_diario(pdia, ex, prods)
    pdd_rep = metricas.produtos_diario(pdia, ex, prods, tipo="reprise")
    sem = metricas.produtos_semanal(pdd, pdia)
    ev = eventos.eventos_relevantes(dados.ocorrencias())
    return {"pdia": pdia, "ex": ex, "prods": prods, "ordem": metricas.ordem_produtos(prods), "pdd": pdd,
            "pdd_rep": pdd_rep, "sem": sem, "ev": ev, "ultima": pdia["data_tv"].max(),
            "ultima_minuto": ex["data_tv"].max(), "primeira": pdia["data_tv"].min()}


@st.cache_data(show_spinner="Lendo o minuto a minuto…")
def faixas_periodo(versao: float, ini: date, fim: date) -> pd.DataFrame:
    return dados.faixas(ini, fim)


@st.cache_data(show_spinner="Lendo o perfil…")
def perfil_todo(versao: float) -> pd.DataFrame:
    return dados.perfil()


@st.cache_data
def bases_dia(versao: float, ini: date, fim: date) -> pd.DataFrame:
    return dados.bases_por_dia(ini, fim)


def base() -> tuple[dict, float]:
    if not config.BASE.exists():
        st.error("A base ainda não foi criada. No VS Code rode a tarefa **Carga inicial da base EPTV**.")
        st.stop()
    v = dados.versao_base()
    return carregar(v), v


# ------------------------------------------------------------------ sidebar e estado

def sidebar(b: dict) -> None:
    ultima_seg = ultima_semana_completa(b["ultima"])
    semanas = [ultima_seg + timedelta(days=7) - timedelta(weeks=i) for i in range(0, 157)]
    semanas = [s for s in semanas if s >= config.DATA_INICIO_ANALISE]  # painel começa em 2024
    if "semana" not in st.session_state:
        st.session_state["semana"] = ultima_seg
    st.sidebar.selectbox("Semana analisada (seg–dom)", semanas, key="semana", format_func=rotulo_semana)

    prox_padrao = proxima_semana()
    futuras = [prox_padrao + timedelta(weeks=i) for i in range(-2, 12)]
    if "proxima" not in st.session_state:
        st.session_state["proxima"] = prox_padrao
    st.sidebar.selectbox("Próxima semana (agenda)", futuras, key="proxima", format_func=rotulo_semana)

    with st.sidebar.expander("Limiares da classificação"):
        st.slider("Variação mínima (%)", 3, 30, 10, key="lim_pct")
        st.slider("Variação mínima (pontos de Rat%)", 0.1, 2.0, 0.5, 0.1, key="lim_pt")
        st.slider("Semanas na média de referência", 2, 8, 4, key="n_media")
    st.sidebar.caption(f"Dados de **{b['primeira']:%d/%m/%Y}** a **{b['ultima']:%d/%m/%Y}** · "
                       f"minuto a minuto até {b['ultima_minuto']:%d/%m}")


def estado() -> dict:
    return {k: st.session_state.get(k) for k in ["semana", "proxima", "lim_pct", "lim_pt", "n_media"]}


def aviso_previa(v: float, seg: date) -> None:
    bd = bases_dia(v, seg, seg + timedelta(days=6))
    live = bd[bd["rank"] < config.RANK_BASE["Consolidado"]]["data_tv"].tolist()
    if live:
        st.warning("Prévia: " + ", ".join(f"{d:%d/%m}" for d in live)
                   + " ainda só em Live. Os números mudam quando o Consolidado for ingerido.", icon="⏳")


# ------------------------------------------------------------------ cálculos usados por páginas e briefing

def calc_comparativos(b: dict, seg: date, e: dict) -> pd.DataFrame:
    marcas = metricas.horario_deslocado(b["pdd"], seg)
    feriados = eventos.datas_marcadas(b["ev"], so_atipicas=True)
    for prod in b["ordem"]:
        dias_prod = b["pdd"][(b["pdd"]["produto"] == prod) & (b["pdd"]["data_tv"] >= seg)
                             & (b["pdd"]["data_tv"] <= seg + timedelta(days=6))]["data_tv"]
        marcados = [f"{d:%d/%m} {feriados[d]}" for d in dias_prod if d in feriados]
        if marcados and prod not in marcas:
            marcas[prod] = "evento: " + "; ".join(marcados)
    return metricas.comparativos(b["sem"], seg, b["ordem"], e["lim_pct"], e["lim_pt"], e["n_media"], marcas)


def calc_diario_semana(b: dict, seg: date) -> pd.DataFrame:
    """Rat% por dia da semana: atual, anterior e mesma semana do ano anterior."""
    blocos = []
    for nome, inicio in [("Semana", seg), ("Semana anterior", seg - timedelta(days=7)),
                         ("Ano anterior", seg - timedelta(days=364))]:
        d = b["pdd"][(b["pdd"]["data_tv"] >= inicio) & (b["pdd"]["data_tv"] <= inicio + timedelta(days=6))]
        blocos.append(d.assign(serie=nome))
    return pd.concat(blocos)


def calc_heat(b: dict, v: float, seg: date, n_semanas: int, sem_feriados: bool = True) -> pd.DataFrame:
    ini = seg - timedelta(weeks=n_semanas - 1)
    fim = min(seg + timedelta(days=6), b["ultima_minuto"])
    fx = faixas_periodo(v, ini, fim)
    excluir = set(eventos.datas_marcadas(b["ev"], so_atipicas=True)) if sem_feriados else set()
    return faixas.heatmap_semana_tipica(fx, b["ex"], excluir)


def calc_janela_chamadas(b: dict, heat: pd.DataFrame, produto: str, ref: date, top: int = 10) -> pd.DataFrame:
    dias = metricas.dias_habituais(b["pdd"], produto, ref)
    horas = metricas.hora_tipica(b["pdd"], produto, ref)
    j = faixas.melhores_blocos_antes(heat, dias, horas, top=top)
    if j.empty:
        return j
    j["dia"] = j["dia_semana"].map(lambda i: DIAS_PT_LONGO[i])
    j["exibição"] = j["dia_exibicao"].map(lambda i: DIAS_PT_LONGO[i])
    return j


def calc_afinidade(b: dict, v: float, produto: str, ini: date, fim: date) -> pd.DataFrame:
    p = perfil_todo(v)
    nomes = b["prods"][(b["prods"]["produto"] == produto) & (b["prods"]["tipo"] == "principal")]["programa"].tolist()
    pp = perfil.perfil_produto(p, nomes, ini, fim)
    if pp.empty:
        return pp
    return perfil.afinidade(pp, perfil.perfil_globo(p, ini, fim))


def calc_onde_chamar(b: dict, v: float, produto: str, publicos: list[str], ini: date, fim: date) -> pd.DataFrame:
    p = perfil_todo(v)
    nomes = b["prods"][b["prods"]["produto"] == produto]["programa"].tolist()
    r = perfil.onde_chamar(p, publicos, ini, fim, excluir=nomes)
    if not r.empty:
        r["dias"] = r["dias"].map(lambda ds: ", ".join(DIAS_PT[i] for i in ds))
    return r


def periodo_perfil(b: dict, v: float, seg: date, semanas: int = 8) -> tuple[date, date]:
    p = perfil_todo(v)
    fim = min(seg + timedelta(days=6), p["data_tv"].max())
    ini = max(seg - timedelta(weeks=semanas - 1), p["data_tv"].min())
    return ini, fim


def produtos_por_dia(b: dict, dias: list[date], ref: date) -> dict[date, list[str]]:
    hab = {p: metricas.dias_habituais(b["pdd"], p, ref) for p in b["ordem"]}
    return {d: [p for p in b["ordem"] if d.weekday() in hab[p]] for d in dias}


def calc_analogos(b: dict, prox: date) -> pd.DataFrame:
    dias = dias_da_semana(prox)
    return analogos.tabela_analogos(b["ev"], b["pdd"], produtos_por_dia(b, dias, prox), b["primeira"])


def siglas(b: dict) -> dict[str, str]:
    return b["prods"].drop_duplicates("produto").set_index("produto")["sigla"].to_dict()


# ------------------------------------------------------------------ gráficos

def fig_diario(diario: pd.DataFrame, produtos: list[str]) -> go.Figure:
    fig = make_subplots(rows=2, cols=2, subplot_titles=produtos, shared_xaxes=False, vertical_spacing=0.16)
    estilos = {"Semana": dict(color=SERIE[0], width=2), "Semana anterior": dict(color=CINZA, width=2),
               "Ano anterior": dict(color=CINZA_CLARO, width=2, dash="dot")}
    for i, prod in enumerate(produtos):
        r, c = i // 2 + 1, i % 2 + 1
        for serie, est in estilos.items():
            d = diario[(diario["produto"] == prod) & (diario["serie"] == serie)].set_index("dia_semana")
            # dias sem exibição viram lacuna na linha, em vez de ligar os vizinhos
            dias_prod = diario[diario["produto"] == prod]["dia_semana"]
            d = d.reindex(range(int(dias_prod.min()), int(dias_prod.max()) + 1))
            d["data_tv"] = pd.to_datetime(d["data_tv"])
            fig.add_trace(go.Scatter(
                x=[DIAS_PT[k] for k in d.index], y=d["rat"], name=serie, line=est, connectgaps=False,
                mode="lines+markers", marker=dict(size=8), legendgroup=serie, showlegend=i == 0,
                customdata=d["data_tv"].dt.strftime("%d/%m/%Y").fillna("sem exibição"),
                hovertemplate="%{customdata}: %{y:.2f}%<extra>" + serie + "</extra>"), row=r, col=c)
        dias_prod = diario[diario["produto"] == prod]["dia_semana"]
        fig.update_xaxes(categoryorder="array", row=r, col=c,
                         categoryarray=DIAS_PT[int(dias_prod.min()):int(dias_prod.max()) + 1])
    fig.update_yaxes(title_text="Rat%", col=1)
    fig = layout_padrao(fig, 540)
    fig.update_layout(margin=dict(t=80), legend=dict(y=1.1))
    return fig


def fig_heat(heat: pd.DataFrame, destaque: pd.DataFrame | None = None) -> go.Figure:
    piv = heat.pivot(index="dia_semana", columns="bloco", values="rat").sort_index()
    prog = heat.pivot(index="dia_semana", columns="bloco", values="programa").reindex_like(piv)
    fig = go.Figure(go.Heatmap(
        z=piv.values, x=[minuto_para_hora(m) for m in piv.columns], y=[DIAS_PT[i] for i in piv.index],
        customdata=prog.values, colorscale=[[i / (len(SEQ_AZUL) - 1), c] for i, c in enumerate(SEQ_AZUL)],
        xgap=1, ygap=2, colorbar=dict(title="Rat%", thickness=10),
        hovertemplate="%{y} %{x}<br>Rat% %{z:.2f}<br>%{customdata}<extra></extra>"))
    if destaque is not None and not destaque.empty:
        fig.add_trace(go.Scatter(
            x=[minuto_para_hora(m) for m in destaque["bloco"]], y=[DIAS_PT[i] for i in destaque["dia_semana"]],
            mode="markers", marker=dict(symbol="circle-open", size=13, color=SERIE[1], line=dict(width=3)),
            name="Melhores blocos para chamar", hoverinfo="skip"))
    fig.update_yaxes(autorange="reversed")
    horas = [minuto_para_hora(m) for m in piv.columns if m % 60 == 0]
    fig.update_xaxes(tickvals=horas, ticktext=[h[:2] + "h" for h in horas])
    fig = layout_padrao(fig, 330)
    fig.update_layout(hovermode="closest")
    return fig


def fig_onde_chamar(r: pd.DataFrame, publicos: list[str]) -> go.Figure:
    r = r.iloc[::-1]
    fig = go.Figure(go.Bar(
        x=r["alvo_mil"], y=r["programa"], orientation="h", marker=dict(color=SERIE[0], cornerradius=4),
        text=r["alvo_mil"].map(lambda x: br(x, 1)), textposition="outside",
        customdata=r[["hora_tipica", "dias", "exibicoes"]].values,
        hovertemplate="%{y}<br>%{x:.1f} mil no público-alvo<br>%{customdata[0]} · %{customdata[1]} · "
                      "%{customdata[2]} exibições<extra></extra>"))
    fig.update_xaxes(title_text=f"Rat# médio (mil indivíduos) · {', '.join(publicos)}")
    fig = layout_padrao(fig, max(320, 26 * len(r) + 80))
    fig.update_layout(hovermode="closest", showlegend=False)
    return fig


def fig_perfil(comp: pd.DataFrame, dimensao: str) -> go.Figure:
    """comp: publico, serie, pct (séries: produto na semana, produto no período, grade Globo)."""
    d = comp[comp["dimensao"] == dimensao]
    ordem = perfil.ORDEM_PUBLICOS[dimensao]
    cores = {0: SERIE[0], 1: SERIE[1], 2: CINZA}
    fig = go.Figure()
    for i, (serie, g) in enumerate(d.groupby("serie", sort=False)):
        g = g.set_index("publico").reindex(ordem)
        fig.add_trace(go.Bar(x=ordem, y=g["pct"], name=serie, marker=dict(color=cores.get(i, CINZA), cornerradius=4),
                             hovertemplate="%{x}: %{y:.1f}%<extra>" + serie + "</extra>"))
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
    fig.update_yaxes(title_text="% do público")
    return layout_padrao(fig, 340)


def fig_semanal_produto(s: pd.DataFrame, ano: pd.DataFrame, marcas: dict) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ano["semana_plot"], y=ano["rat"], name="Ano anterior",
                             line=dict(color=CINZA_CLARO, width=2, dash="dot"), mode="lines",
                             hovertemplate="%{y:.2f}%<extra>Ano anterior</extra>"))
    texto = [marcas.get(w, "") for w in s["semana"]]
    fig.add_trace(go.Scatter(
        x=s["semana"], y=s["rat"], name="Rat% semanal", mode="lines+markers", line=dict(color=SERIE[0], width=2),
        marker=dict(size=8, color=[SERIE[0] if c else "rgba(0,0,0,0)" for c in s["comparavel"]],
                    line=dict(color=SERIE[0], width=2)),
        customdata=texto, hovertemplate="%{y:.2f}%<br>%{customdata}<extra>Semana</extra>"))
    fig.update_yaxes(title_text="Rat%")
    return layout_padrao(fig, 340)


def fig_curva(cur: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for i, (d, g) in enumerate(cur.groupby("data_tv")):
        cor = SERIE[i % len(SERIE)]
        nome = f"{DIAS_PT[d.weekday()]} {d:%d/%m}"
        # intervalos no meio do produto (ex.: horário eleitoral) ficam como lacuna na linha
        fim_produto = g.loc[g["no_ar"], "rel"].max()
        visivel = g["no_ar"] | (g["rel"] < 0) | (g["rel"] > fim_produto)
        fig.add_trace(go.Scatter(
            x=g["rel"], y=g["rat"].where(visivel),
            name=nome, mode="lines", line=dict(color=cor, width=2),
            customdata=g["minuto"].map(minuto_para_hora),
            hovertemplate="%{customdata} · %{y:.2f}%<extra>" + nome + "</extra>"))
    fig.add_vline(x=0, line=dict(color=CINZA, width=1, dash="dot"))
    fig.update_xaxes(title_text="minutos desde o início do produto (antes de 0 = herança)")
    fig.update_yaxes(title_text="Rat%")
    return layout_padrao(fig, 380)


def fig_concorrencia(c: pd.DataFrame) -> go.Figure:
    tot = c[c["dimensao"] == "Sexo"].groupby("emissora")["rat_abs"].sum().sort_values()
    cores = [SERIE[0] if e == config.EMISSORA_PROPRIA else CINZA for e in tot.index]
    fig = go.Figure(go.Bar(x=tot.values, y=tot.index, orientation="h", marker=dict(color=cores, cornerradius=4),
                           text=[br(x, 1) for x in tot.values], textposition="outside",
                           hovertemplate="%{y}: %{x:.1f} mil indivíduos<extra></extra>"))
    fig.update_xaxes(title_text="Rat# médio no horário do produto (mil indivíduos)")
    fig = layout_padrao(fig, 220)
    fig.update_layout(hovermode="closest", showlegend=False)
    return fig


def cor_delta(v) -> str:
    """Fundo divergente (vermelho = queda, azul = alta, cinza = neutro) para tabelas."""
    if v is None or pd.isna(v):
        return ""
    if v <= -15:
        return f"background-color: {DIV['neg']}; color: white"
    if v <= -5:
        return f"background-color: {DIV['neg_suave']}; color: #0b0b0b"
    if v < 5:
        return f"background-color: {DIV['neutro']}; color: #0b0b0b"
    if v < 15:
        return f"background-color: {DIV['pos_suave']}; color: #0b0b0b"
    return f"background-color: {DIV['pos']}; color: white"
