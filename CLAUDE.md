# Contexto para IA · Painel Promo · Produtos Locais EPTV

Leia este arquivo antes de mexer em qualquer coisa nesta pasta. Os READMEs detalham o uso; aqui estão o mapa, as regras de negócio e o que não pode quebrar.

## Objetivo
Painel Streamlit que entende a **semana de TV anterior (segunda a domingo)** dos produtos locais da EPTV (Globo, praça Grande Campinas) para orientar o **time de Promo** na próxima semana: o que reforçar, onde e para quem chamar, e quais eventos vêm por aí. Ele mostra **só painéis e tabelas, sem texto gerado por IA**. O usuário (analista de audiência da EPTV) escreve o direcionamento.

## Estrutura
```
TERÇA-FEIRAS/
├── BASE_HISTORICA_V1_RF.xlsx   referência diária por programa (2014+); REGRAVADA pela rotina (com backup)
├── BASE_SEMANAL_V1_RF.xlsx     referência semanal; REGRAVADA pela rotina; o painel não lê (recalcula)
├── INGESTAO DIARIA *.xlsx      exports Instar já carregados (histórico e dias avulsos)
├── PERFIL_TEMP.xlsx            perfil por público, 4 emissoras, desde 01/08/2026
├── _nao_usados/                arquivos tirados de uso (não reintroduzir sem pedido)
├── agente_cronologia/          coletor de eventos (Python stdlib + tzdata, SQLite) → Ocorrências
├── promo_semanal/              o painel
│   ├── config.py               caminhos, DATA_INICIO_ANALISE, prioridades, limiar comparável
│   ├── config/produtos.csv     produto ↔ nomes de programa no Instar (editável)
│   ├── config/times_regiao.csv times destacados no futebol
│   ├── ingestao/               leitores (calamine), base (DuckDB, upsert), atualizar, carga_inicial, exportar_referencias
│   ├── analise/                funções puras: semana_tv, metricas, faixas, perfil, eventos, analogos, export, dados
│   ├── app/app.py + comum.py   Streamlit (somente leitura); paginas/1_semana … 7_base
│   ├── base/eptv_promo.duckdb  BASE ÚNICA (não versionar, não editar à mão)
│   ├── entrada/                onde chegam os arquivos diários (+ README com os cartões técnicos)
│   └── tests/                  pytest
└── .vscode/tasks.json          rotina: Ctrl+Shift+B = Atualizar tudo (cronologia + base EPTV)
```

## Os 8 produtos (escopo fechado)
| Produto | Nomes no Instar | Grade |
|---|---|---|
| BOM DIA CIA (BDC) | BOM DIA CIDADE | seg–sex ~07:30 |
| JORNAL EPTV 1 (JE1) | JORNAL DA EPTV 1 (desde 06/2025), JORNAL DA EPTV (antes) | seg–sáb ~11:45 |
| GLOBO ESPORTE (GE) | GLOBO ESPORTE | seg–sáb ~13:00 |
| JORNAL EPTV 2 (JE2) | JORNAL DA EPTV 2A EDICAO SS / SB / (até 2019) | seg–sáb ~19:10 |
| EP AGRO | EP AGRO | sáb ~08:10 |
| TERRA DA GENTE (TDG) | TERRA DA GENTE VES (inédito); MAD 1 = reprise, tratada à parte | sáb ~14:10 |
| MAIS CAMINHOS (MC) | MAIS CAMINHOS VES, MAIS CAMINHOS | sáb ~14:45 |
| ESPIA SÓ | ESPIA SO MAT, ESPIA SO | dom ~06:30 |

Fora do escopo: BOL EPTV CIDADE*, ELEICOES EPTV*, especiais. O mapeamento vive só em `config/produtos.csv`; nunca coloque nomes de programa direto no código.

## Fluxo de dados
1. O usuário exporta do Instar os arquivos de D-1 (PROGRAMAS, FAIXAS e PERFIL) e solta em `promo_semanal/entrada/`.
2. A tarefa `Atualizar cronologia` roda `agente_cronologia/run_daily.ps1`, que busca os jogos na ESPN e grava `entrada/Ocorrencias_agente.csv`.
3. A tarefa `Atualizar base EPTV` roda `ingestao/atualizar.py`: detecta o tipo pelo **conteúdo** (abas e linha de título; o nome do arquivo não importa), faz o upsert no DuckDB, deriva `programas_dia` dos dias sem referência, regrava BASE_HISTORICA e BASE_SEMANAL (com backup em `backup/`, os 10 mais recentes) e move os arquivos para `entrada/processados/AAAA-MM-DD/`.
4. O painel (`app/app.py`, porta **8502**; a 8501 é de outro app do usuário) lê o DuckDB em `read_only`, abrindo e fechando a conexão a cada consulta, e só considera datas a partir de `DATA_INICIO_ANALISE` (2024-01-01).

### Tabelas do DuckDB
`programas_dia` (≈ BASE_HISTORICA) · `exibicoes` (uma linha por exibição, com horário e Rat#) · `faixas_minuto` (Globo, 1.440 min/dia) · `perfil` (formato longo: dimensão/público/Rat#, 4 emissoras) · `ocorrencias` · `log_ingestao` (hash do arquivo; conteúdo repetido é pulado).

## Regras que NÃO podem mudar sem pedido explícito
- **Dia de TV = 06:00 a 29:59.** Horas ≥ 24 pertencem à data anterior. `minuto` = minutos desde 06:00 (0–1439). Nunca converta para data civil.
- **Semana = segunda a domingo**, identificada pela segunda-feira.
- **Upsert por dia inteiro com prioridade.** Base: Consolidado (2) > Live (1). Fonte em `programas_dia`: referencia (3) > derivado_consolidado (2) > derivado_live (1). Grava se rank novo ≥ rank existente. As chaves de data são sempre `datetime.date` (já houve bug com Timestamp × date sobrescrevendo a referência).
- **Linha diária derivada** (dia ausente da BASE_HISTORICA): com minuto a minuto, Rat% = média dos minutos do programa e Shr% TLE = média de Rat ÷ média de TLE (TLE = Rat%/Shr% do minuto); sem minuto a minuto, média das exibições ponderada pela duração. A data inteira assume a pior fonte entre seus programas.
- **Réplica da BASE_SEMANAL** (validada: Rat/Shr/Exibições/Comparável 100%, habituais 99,97%): Rat% e Shr% = média simples dos dias; Exibições = dias com exibição; Dias base = dias com dado na semana; Exib habituais = **mediana com arredondamento bancário** (`np.round`) de todo o histórico do programa; Completa = 7 dias; Comparável = Completa e Exibições/Habituais ≥ 0,6.
- **Classificação** (limiares na sidebar, padrão |Δ%| ≥ 10 **e** |Δpt| ≥ 0,5 contra a média das 4 semanas comparáveis anteriores): Reforçar, Aproveitar, Estável, Atípico (não comparável, horário deslocado > 30 min ou feriado/evento **nacional** no dia) e Sem exibição.
- **Eventos atípicos/exclusões** usam `datas_marcadas(ev, so_atipicas=True)`: feriados, pontos facultativos e acontecimentos de abrangência "Brasil…". Eventos locais (ex.: Expoflora, todo fim de semana de setembro) **não** marcam atípico. O mapa de calor nunca pode perder um dia da semana inteiro.
- **Ano anterior** = semana − 364 dias (mesmo dia da semana).
- **Produto partido no dia** (ex.: JE1 interrompido pelo horário eleitoral): use os segmentos reais (`metricas.segmentos_produto`), nunca o intervalo do primeiro início ao último fim.
- **"Onde chamar"** exclui programas com < 3 exibições ou que não foram ao ar na última semana do período.
- Exportação das bases de referência mantém o layout original: aba `Crosstab` (Data dd/mm/aaaa · Nome Programa · Rat% · Shr% [Total Ligados Especial]) e aba `Semanal`.

## Formato dos exports do Instar (detalhe em `promo_semanal/entrada/README.md`)
- Leia **sempre com `engine="calamine"`**. O openpyxl quebra nos estilos do Instar.
- Linha 0 = título com a base (`…|Live)` ou `…|Consolidado)`), linha 1 = cabeçalho, linha seguinte = `Total` (descartar).
- PROGRAMAS: aba `Programas`. FAIXAS: aba `Faixas Horárias` (o export grande também traz `Programas`). PERFIL: aba `Programas` com a linha 2 começando em `Variáveis >>`; a dimensão sai do nome do público (AB1/B2/C1/C2/DE → Classe, "anos" → Idade, HOMENS/MULHERES → Sexo).
- CSVs da cronologia: separador `;`, encoding `utf-8-sig`. Calendário é ignorado de propósito.

## Agente de cronologia (`agente_cronologia/`)
- `config/settings.json`: `sources = ["espn"]`, só ligas brasileiras, sul-americanas e da Seleção (a Série C da ESPN volta vazia), sem OpenFootball. `export_filtro` deixa só feriados, pontos facultativos, datas comemorativas, acontecimentos e futebol relevante (~4,4 mil de 39 mil registros). `promo_entrada` entrega o CSV ao painel.
- A entrega acontece no `__main__.export` (camada de linha de comando), **não** em `core.export`, para os testes não escreverem na pasta real.
- O GPT (OpenAI) fica **desligado** na rotina. Só faz sentido com uma fonte de notícias (`campinas`) e a chave no `.env`, e os candidatos passam por revisão humana. Não ligue sem o usuário pedir.
- Feriados de 2027 não vêm de API: é preciso ampliar `end_date` e rodar `import-csv` com feriados validados.

## Comandos
```powershell
# painel (cwd promo_semanal)
python ingestao/atualizar.py [--forcar] [--sem-referencias]
python ingestao/carga_inicial.py --recriar        # reconstrói a base (~1 min)
python -m pytest -q tests                          # 21 testes
python -m streamlit run app/app.py --server.port 8502 --server.headless true
# agente (cwd agente_cronologia)
python -m cronologia update | export | status
python -m unittest discover -s tests               # 28 testes
```
- Python 3.14, pandas 3, Streamlit 1.64, DuckDB, plotly, python-calamine (já instalados).
- Em scripts com acentos, use `PYTHONIOENCODING=utf-8`. O Bash do ambiente é Git Bash; o caminho tem espaços e "Ç": sempre entre aspas.
- Para testar páginas sem navegador: `streamlit.testing.v1.AppTest` (selectboxes de data da sidebar quebram o `set_value`; passe valores por `at.session_state[...]` antes de `run()`).
- Depois de mudar módulos, **reinicie** o Streamlit; ele não recarrega `analise/` e `comum.py` sozinho.

## Convenções de código e interface
- Português nos nomes, comentários e interface. Funções de cálculo em `analise/`, sem Streamlit. Páginas e briefing reaproveitam os mesmos cálculos e gráficos de `app/comum.py`.
- Números no padrão brasileiro (`comum.br`, `comum.formatar`). O `st.dataframe` mostra NaN como "None", então formate como texto com "–".
- Gráficos seguem a paleta de referência (azul `#2a78d6` para a série principal, cinza para comparação, escala azul sequencial, divergente vermelho↔cinza↔azul). Status sempre com ícone + rótulo. Nunca dois eixos y.
- Não adicione texto gerado ou "insights" automáticos na tela: decisão do usuário.

## Restrições e cuidados
- **Dados IBOPE/Kantar:** o Cartão Técnico diz que eles não podem ser usados como insumo de sistemas internos nem de modelos de IA sem anuência do IBOPE. Nunca envie dados de audiência para serviços externos ou LLMs. O uso no painel ainda precisa ser confirmado com a área de Pesquisa.
- Não apague nem sobrescreva arquivos da pasta TERÇA-FEIRAS fora da rotina (que faz backup). Para tirar algo de uso, mova para `_nao_usados/`.
- Não há grade futura. A agenda mostra os produtos habituais por dia da semana, e as Ocorrências não dizem qual jogo a Globo transmite.
- O PERFIL começa em 01/08/2026. As amostras de DE, 12–17, 18–24 e 4–11 são pequenas (57–74 casos), então leia em períodos de semanas.
