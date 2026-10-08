# TERÇA-FEIRA · Painel Promo · Produtos Locais EPTV

Painel semanal (semana de TV de segunda a domingo) que orienta o time de Promo da EPTV sobre os 8 produtos locais. Ele mostra o que reforçar, onde e para quem chamar, e quais eventos vêm na próxima semana.

| Pasta | O que é |
|---|---|
| [promo_semanal/](promo_semanal/README.md) | Painel Streamlit, ingestão diária (DuckDB) e briefing exportável |
| [promo_semanal/entrada/](promo_semanal/entrada/README.md) | Arquivos diários do Instar e o cartão técnico de cada um |
| [agente_cronologia/](agente_cronologia/README.md) | Coletor de feriados, datas e futebol que alimenta a agenda |
| [CLAUDE.md](CLAUDE.md) | Contexto completo para assistentes de IA |

**Este repositório tem só código e documentação.** Os dados de audiência (exports do Instar, BASE_HISTORICA, BASE_SEMANAL, PERFIL e a base DuckDB) são IBOPE/Kantar de uso restrito e ficam apenas na máquina local, bloqueados pelo `.gitignore`. Para rodar, copie esses arquivos para a raiz da pasta e execute `python promo_semanal/ingestao/carga_inicial.py --recriar`.
