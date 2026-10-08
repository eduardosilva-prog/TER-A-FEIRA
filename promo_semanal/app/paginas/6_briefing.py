from datetime import date, timedelta

import pandas as pd
import streamlit as st

import comum
from analise import eventos, export, perfil as perfil_mod
from analise.semana_tv import DIAS_PT, rotulo_semana

b, v = comum.base()
e = comum.estado()
seg, prox = e["semana"], e["proxima"]

st.title("Briefing para o time de Promo")
st.caption(f"Semana analisada {rotulo_semana(seg)} · próxima semana {rotulo_semana(prox)}. "
           "Os arquivos trazem os mesmos números e gráficos do painel.")

SECOES = {
    "semana": "Quadro da semana (classificação dos produtos)",
    "diario": "Dia a dia dos produtos diários",
    "chamadas": "Onde chamar (janelas e programas por produto)",
    "perfil": "Perfil e afinidade por produto",
    "agenda": "Agenda da próxima semana e datas análogas",
}
escolha = {k: st.checkbox(t, True, key=f"sec_{k}") for k, t in SECOES.items()}
dim_alvo = st.radio("Dimensão do público-alvo em 'Onde chamar'", ["Idade", "Classe", "Sexo"], horizontal=True)


def fmt_dia(d: date) -> str:
    return f"{DIAS_PT[d.weekday()]} {d:%d/%m}"


def montar() -> tuple[dict, list]:
    abas, secoes = {}, []
    if escolha["semana"]:
        comp = comum.calc_comparativos(b, seg, e)
        t = comp[["produto", "classe", "motivo", "rat", "shr", "rat_abs", "d_pct_ant", "d_pct_media", "d_pct_ano",
                  "exibicoes", "exib_habituais"]].rename(columns={
            "produto": "Produto", "classe": "Direcionamento", "motivo": "Motivo", "rat": "Rat%", "shr": "Shr%",
            "rat_abs": "Rat# (mil)", "d_pct_ant": "Δ% sem. ant.", "d_pct_media": f"Δ% média {e['n_media']} sem.",
            "d_pct_ano": "Δ% ano ant.", "exibicoes": "Exibições", "exib_habituais": "Habituais"})
        abas["Semana"] = t
        ev = eventos.eventos_semana(b["ev"], seg)
        itens = [t]
        if not ev.empty:
            ev_t = ev.assign(Dia=ev["data"].map(fmt_dia))[["Dia", "categoria", "titulo", "horario"]].rename(
                columns={"categoria": "Tipo", "titulo": "Evento", "horario": "Hora"})
            abas["Eventos da semana"] = ev_t
            itens += [("h3", "Eventos da semana"), ev_t]
        secoes.append((f"Quadro da semana · {rotulo_semana(seg)}", itens))

    if escolha["diario"]:
        d = comum.calc_diario_semana(b, seg)
        diarios = [p for p in b["ordem"] if len(comum.metricas.dias_habituais(b["pdd"], p, seg + timedelta(days=7))) >= 4][:4]
        abas["Dia a dia"] = d.assign(Dia=d["data_tv"].map(fmt_dia))[["serie", "produto", "Dia", "rat", "shr", "rat_abs"]].rename(
            columns={"serie": "Série", "produto": "Produto", "rat": "Rat%", "shr": "Shr%", "rat_abs": "Rat# (mil)"})
        secoes.append(("Dia a dia dos produtos diários", [comum.fig_diario(d, diarios)]))

    if escolha["chamadas"] or escolha["perfil"]:
        heat = comum.calc_heat(b, v, seg, 4)
        ini, fim = comum.periodo_perfil(b, v, seg)
        jan_all, rank_all, af_all, itens_ch, itens_pf = [], [], [], [], []
        if escolha["chamadas"]:
            itens_ch.append(comum.fig_heat(heat))
            itens_ch.append("Semana típica da Globo (média de 4 semanas, sem feriados) · Rat% por bloco de 15 min.")
        for prod in b["ordem"]:
            af = comum.calc_afinidade(b, v, prod, ini, fim)
            if escolha["chamadas"]:
                jan = comum.calc_janela_chamadas(b, heat, prod, seg + timedelta(days=7))
                if not jan.empty:
                    jt = jan[["dia", "hora", "programa", "rat", "dias_antes", "exibição"]].rename(columns={
                        "dia": "Dia", "hora": "Bloco", "programa": "Programa típico", "rat": "Rat%",
                        "dias_antes": "Dias antes", "exibição": "Para a exibição de"})
                    jan_all.append(jt.assign(Produto=prod))
                    itens_ch += [("h3", prod), jt.head(5)]
                if not af.empty:
                    alvo = perfil_mod.publicos_alvo(af, dim_alvo)
                    r = comum.calc_onde_chamar(b, v, prod, alvo, ini, fim)
                    if not r.empty:
                        rank_all.append(r.assign(Produto=prod, Publico=", ".join(alvo)))
                        itens_ch.append(comum.fig_onde_chamar(r.head(10), alvo))
            if escolha["perfil"] and not af.empty:
                at = af[["dimensao", "publico", "pct", "pct_globo", "afinidade"]].rename(columns={
                    "dimensao": "Dimensão", "publico": "Público", "pct": "% produto", "pct_globo": "% grade",
                    "afinidade": "Afinidade"})
                af_all.append(at.assign(Produto=prod))
                itens_pf += [("h3", prod), at]
        if jan_all:
            abas["Janelas de chamada"] = pd.concat(jan_all)
        if rank_all:
            abas["Programas p público-alvo"] = pd.concat(rank_all).rename(columns={
                "programa": "Programa", "alvo_mil": "Rat# alvo (mil)", "exibicoes": "Exibições",
                "hora_tipica": "Hora típica", "dias": "Dias"})
        if af_all:
            abas["Perfil e afinidade"] = pd.concat(af_all)
        if itens_ch:
            secoes.append(("Onde chamar", itens_ch))
        if itens_pf:
            secoes.append((f"Perfil e afinidade ({ini:%d/%m}–{fim:%d/%m})", itens_pf))

    if escolha["agenda"]:
        ev = eventos.eventos_semana(b["ev"], prox)
        ag = ev.assign(Dia=ev["data"].map(fmt_dia))[["Dia", "categoria", "titulo", "horario", "grupo"]].rename(
            columns={"categoria": "Tipo", "titulo": "Evento", "horario": "Hora", "grupo": "Destaque"})
        abas["Agenda próxima semana"] = ag
        itens = [ag]
        an = comum.calc_analogos(b, prox)
        if not an.empty:
            at = an.assign(**{"Dia-alvo": an["dia_alvo"].map(fmt_dia), "Data análoga": an["data_analoga"].map(
                lambda d: f"{d:%d/%m/%Y} ({DIAS_PT[d.weekday()]})")})
            at["Exibido"] = at["exibido"].map({True: "sim", False: "não"})
            at = at[["Dia-alvo", "evento", "Data análoga", "produto", "Exibido", "rat", "rat_base", "delta_pct"]].rename(
                columns={"evento": "Evento", "produto": "Produto", "rat": "Rat%", "rat_base": "Rat% base 4 sem.",
                         "delta_pct": "Δ%"})
            abas["Datas análogas"] = at
            itens += [("h3", "Produtos em datas análogas"), at,
                      "Δ% contra a média do mesmo dia da semana nas 4 semanas anteriores (sem feriados)."]
        secoes.append((f"Próxima semana · {rotulo_semana(prox)}", itens))
    return abas, secoes


if st.button("Gerar briefing", type="primary"):
    with st.spinner("Montando…"):
        abas, secoes = montar()
        titulo = f"Briefing Promo · Produtos Locais · {rotulo_semana(seg)}"
        sub = (f"Base até {b['ultima']:%d/%m/%Y} · Total Domicílios · Grande Campinas · "
               f"Próxima semana {rotulo_semana(prox)}")
        st.session_state["briefing"] = (export.excel(abas), export.html(titulo, sub, secoes), seg)

if "briefing" in st.session_state:
    xls, htm, s = st.session_state["briefing"]
    nome = f"briefing_promo_{s:%Y-%m-%d}"
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Excel", xls, f"{nome}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    c2.download_button("⬇️ HTML (abre no navegador; imprima em PDF)", htm, f"{nome}.html", "text/html", width="stretch")
    st.caption("Dados IBOPE/Kantar de uso interno, conforme o Cartão Técnico.")
