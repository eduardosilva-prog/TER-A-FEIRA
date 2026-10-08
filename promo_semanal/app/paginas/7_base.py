import streamlit as st

import comum
from analise import dados

b, v = comum.base()

st.title("Sobre a base")
st.caption("O painel só lê. Para atualizar, solte os arquivos do Instar em `promo_semanal/entrada/` e rode no VS Code "
           "a tarefa **Atualizar base EPTV** (Ctrl+Shift+B).")

from ingestao.base import status_base  # noqa: E402

with dados._con() as con:
    st.subheader("Cobertura")
    st.dataframe(status_base(con), hide_index=True, width="stretch")

st.subheader("Últimas ingestões")
st.dataframe(dados.log_ingestao(30), hide_index=True, width="stretch")

st.subheader("Produtos e nomes na base")
st.dataframe(b["prods"], hide_index=True, width="stretch")
st.caption("Para incluir um novo nome de programa (ex.: troca de nomenclatura), edite `config/produtos.csv`.")

st.subheader("Limitações")
st.markdown("""
- **Sem grade futura**: a agenda mostra os eventos, não o que vai ao ar. Os produtos listados por dia são os habituais.
- **Futebol**: as Ocorrências não indicam qual jogo a Globo transmite; a ausência de registro não significa ausência de evento.
- **Live × Consolidado**: dias só em Live aparecem como *prévia* e são substituídos quando chega o Consolidado.
- **Shr% de dias novos**: quando o dia não vem da BASE_HISTORICA, o Shr% [Total Ligados Especial] é calculado do minuto a minuto
  (diferença típica de até 0,3 pt para o Crosstab do Instar).
- **Perfil**: começa em 01/08/2026; comparações de perfil com o ano anterior só a partir de 08/2027.
- **Uso dos dados**: o Cartão Técnico do IBOPE restringe o uso em sistemas internos sem anuência; confirmar com a Pesquisa.
""")
