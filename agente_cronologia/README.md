# Agente de cronologia — Brasil e Região de Campinas

## Configuração EPTV (painel Promo) — leia primeiro

Este agente alimenta a página **Próxima semana** e as marcas de semana atípica do painel em `../promo_semanal`.
A configuração em `config/settings.json` foi ajustada para coletar e entregar **só o que o painel usa**:

| Item | Configuração | Motivo |
|---|---|---|
| `sources` | `["espn"]` | Única fonte com dado novo útil ao painel: jogos e resultados. Campinas e IBGE geram só publicações, que o painel não usa. OpenFootball cobre ligas estrangeiras. |
| `espn_leagues` | Séries A e B, Paulistão, Copa do Brasil, Libertadores, Sul-Americana, Copa América, Copa do Mundo, Mundial de Clubes, Eliminatórias, amistosos (masculino e feminino) | Competições com times brasileiros ou com a Seleção. A Série C da ESPN volta vazia, e o Guarani aparece pelo Paulistão e pela Copa do Brasil. |
| `openfootball_*` | vazias | Ligas europeias, asiáticas e dos EUA não interessam ao painel. |
| `export_filtro` | Feriados, pontos facultativos, datas comemorativas, acontecimentos, mais futebol das competições acima ou com a Seleção | O `ocorrencias.csv` sai com cerca de 4,4 mil registros relevantes, em vez de 39 mil. O banco `state/` continua com tudo. |
| `promo_entrada` | `../promo_semanal/entrada/Ocorrencias_agente.csv` | Cada `init`, `update`, `extract`, `review` ou `export` entrega o arquivo para o painel ingerir. |
| IA (GPT) | desligada na rotina | Sem fonte de notícias, não há documento para extrair. Para ligar: inclua `"campinas"` em `sources`, preencha `OPENAI_API_KEY` no `.env` e rode `python -m cronologia update --with-ai`. Os candidatos vão para `exports/revisao.csv` e só entram depois de aprovados com `review`. |

Rotina: no VS Code, `Ctrl+Shift+B` → **Atualizar tudo (cronologia + base EPTV)**. Roda `run_daily.ps1` e depois a ingestão do painel.
Para remover o filtro e exportar tudo de novo, apague a chave `export_filtro`.
Feriados e datas de **2027** não vêm de nenhuma API. É preciso ampliar `end_date` e importar os feriados validados com `import-csv` (veja "Feriados e curadoria").


Projeto executável em Python com GPT mini para alimentar uma base diária de notícias,
futebol e acontecimentos. O modelo padrão é `gpt-5-mini`, configurável em `.env`.
Requer Python 3.11+ (recomendado 3.12). A única dependência é `tzdata`, para
garantir os fusos IANA também no Windows; banco e processamento usam biblioteca padrão.

## Começar no Windows / VS Code

Extraia o ZIP e abra a pasta `agente_cronologia` no VS Code. No terminal PowerShell:

```powershell
python --version
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Preencha **localmente** sua chave da API da OpenAI em `OPENAI_API_KEY`.
Não envie a chave no chat nem versione `.env`. A assinatura ChatGPT não substitui
créditos/limites da API. O pacote não contém chave e não ativa cobrança ao importá-lo.

```powershell
python -m cronologia init
python -m cronologia status
python -m cronologia update --sources campinas ibge espn
python -m cronologia extract --limit 5
python -m cronologia export
```

`init` importa os **39.192 registros** da base inicial; é idempotente. **Não** cria documentos
para extrair acontecimentos antigos por GPT: as notícias históricas do CSV têm somente
títulos/metadados limitados. Para processá-las com IA, recolete as fontes usando `backfill`.
`update` busca notícias recentes e jogos; `extract` processa apenas documentos novos ou alterados.
`update --with-ai` reúne os dois passos. Os candidatos de acontecimentos ficam em revisão.

## O que já vem e o que será atualizado

- `seed/Ocorrencias_2024_2026.csv`: base inicial com 39.192 registros; coleta histórica até 08/10/2026.
- `state/chronology.sqlite`: banco criado ao executar `init`; chave primária por registro.
- `state/raw/`: última resposta por URL, hash e data da consulta; não é arquivo de todas as versões.
- `exports/ocorrencias.csv`: fatos, publicações, partidas e acontecimentos aprovados.
- `exports/calendario.csv`: todos os dias de 2024 a 2026, incluindo os vazios.
- `exports/revisao.csv`: candidatos do GPT mini aguardando avaliação, com evidência e fonte.

Notícias usam **data de publicação**, nunca a data inferida do acontecimento. ESPN usa
`America/Sao_Paulo`; OpenFootball mantém data/horário original com fuso desconhecido.
Placares futuros ou sem conclusão confirmada ficam vazios. Não há promessa de cobertura universal.
No IBGE, os parâmetros `de`/`ate` foram confirmados em consulta como **MM-DD-AAAA**,
enquanto `data_publicacao` na resposta é **DD/MM/AAAA HH:MM:SS**. O coletor trata os dois
formatos separadamente e filtra novamente o intervalo após interpretar a resposta.

## Configuração e custo

Edite `config/settings.json`. Limites iniciais: 10 documentos por execução, 20 chamadas
de IA por dia no fuso configurado, 18.000 caracteres de texto e até 4.000 tokens de saída por chamada.
O limite é persistido **antes** da chamada; falhas e timeouts também o consomem. Não é um teto
monetário da conta OpenAI; configure seu limite de gastos no projeto da API.
`--limit` muda os documentos desta execução, mantendo o teto diário. O limite de tokens de saída
inclui o orçamento utilizado pelo modelo; respostas incompletas permanecem pendentes para tentar depois.

```text
OPENAI_API_KEY=sua_chave_local
OPENAI_MODEL=gpt-5-mini
```

É possível substituir `OPENAI_MODEL` por outro modelo compatível com Responses + Structured Outputs.
Não há fallback silencioso de modelo. Chamadas são HTTP diretas para a API oficial, com `store:false`.
O corpo das notícias selecionadas é enviado à OpenAI; só configure fontes adequadas para esse uso.
GPT recebe documentos como dados e não executa instruções contidas neles.

## Carga histórica e atualização

```powershell
# Recuperar metadados e documentos de notícias desde 2024; nenhuma IA nessa coleta.
python -m cronologia backfill --sources campinas ibge --start 2024-01-01 --end 2026-10-08

# Coleta completa de futebol (pode levar vários minutos).
python -m cronologia backfill --sources espn openfootball --start 2024-01-01 --end 2026-12-31

# Executar todas as fontes e IA.
python -m cronologia update --with-ai

# Processar a fila gradualmente, respeitando o limite diário.
python -m cronologia extract --limit 10
```

Sem `--start`, `update` consulta notícias e partidas desde 7 dias atrás, com sobreposição;
vai até `end_date` para conservar programação futura. A coleta de ESPN consulta cada ano inteiro
envolvido, mas só incorpora o intervalo pedido. Correções de datas/resultados mais antigos devem
ser reconciliadas com `backfill` periódico. Como o ID da ESPN é estável, um jogo adiado atualiza
o mesmo registro. IDs diferentes de possíveis duplicatas não são fundidos por nome.

OpenFootball utiliza identidade baseada em arquivo + posição, conforme a carga inicial.
Cada arquivo retornado é substituído atomicamente no intervalo consultado: evita misturar posições
de versões diferentes. Um arquivo 404 é contado como ausente e **não apaga** o histórico.
Um arquivo sem partidas também preserva o histórico e é sinalizado em `empty_files`.
Arquivos de temporadas/competições inexistentes são esperados; consulte `missing_files` nos logs.

Não há garantia de contrato público para a API da ESPN/Prefeitura. O agente detecta alterações
de esquema e devolve falha, em vez de gravar dados com estrutura inesperada. Na ESPN, 1.000 eventos
é tratado como possível truncamento. A Prefeitura deve manter ordenação por criação para o corte
de páginas funcionar; `max_pages` atingido gera falha. Recomendação: executar reconciliação mensal.

## Revisar acontecimentos do GPT mini

O modelo extrai data inicial/final, local, categoria, status e citação de até 25 palavras.
O código valida data, intervalo, esquema e correspondência literal da citação ao documento.
Isso **não prova** que a interpretação da data está correta; os candidatos não entram
automaticamente na cronologia como fatos. Anúncio antigo continua sendo anúncio.

Abra `exports/revisao.csv`, leia a fonte e use o ID do candidato:

```powershell
python -m cronologia review --id ID_DO_CANDIDATO --decision approved --reviewer "Seu nome"
python -m cronologia review --id ID_DO_CANDIDATO --decision rejected --reviewer "Seu nome"
```

Aprovar registra o acontecimento na **data inicial**, preservando a data final nos detalhes.
Não multiplica um festival por todos os dias: intervalos não comprovam funcionamento diário.
Matérias diferentes sobre o mesmo evento podem gerar candidatos distintos; rejeite a duplicata.
Se o documento ou modelo/prompt mudar, uma nova extração válida recoloca os candidatos em revisão
e retira os acontecimentos aprovados daquela versão até nova avaliação.
Casos sem evidência literal, datas ambíguas, recusa ou saída incompleta não são aprovados pelo código.
Para metadados sem artigo acessível, o modelo recebe somente o que foi coletado e pode retornar vazio.

## Feriados e curadoria

Os feriados e datas selecionadas de 2024–2026 vêm da carga inicial. Não são inventados pelo GPT.
**Esta versão não monitora automaticamente Diário Oficial, leis novas nem todos os organizadores.**
O agente automatiza Campinas, IBGE e futebol; extrai candidatos dessas notícias. Para ampliar fontes,
adicione um coletor em `collectors.py` e o domínio permitido em `net.py`.
Campinas: aniversário de 14/07 está como data comemorativa; Dia do Evangélico somente em 2026.
Pontos facultativos municipais detalhados apenas para 2026, conforme a base inicial.

Para adicionar uma portaria/acontecimento validado, crie CSV com os mesmos cabeçalhos e separador `;`:

```powershell
python -m cronologia import-csv meus_eventos_validados.csv
```

Use IDs próprios estáveis, como `manual-campinas-lei-123-data`; preserve a URL da fonte normativa.
Novos anos exigem ampliar `end_date` e cadastrar/revalidar seus feriados locais. O calendário diário
se estende automaticamente; as leis municipais não. O agente não pesquisa toda a internet livremente.

## Executar diariamente

No Agendador de Tarefas do Windows, crie uma tarefa diária com:

```text
Programa: powershell.exe
Argumentos: -NoProfile -File "C:\CAMINHO\agente_cronologia\run_daily.ps1"
```

Use o Python disponível no PATH da conta da tarefa ou troque `python` pelo caminho absoluto no script.
No Linux, use cron (horário do servidor; não presume o fuso de Brasília):

```cron
0 9 * * * cd /caminho/agente_cronologia && /usr/bin/python3 -m cronologia update --with-ai >> state/cron.log 2>&1
```

Crie `state` com `init` antes do agendamento. Para a reconciliação mensal, agende `backfill` separadamente.
Lock do sistema operacional impede execuções simultâneas no mesmo diretório.

Docker, para executar uma coleta e terminar:

```sh
docker build -t agente-cronologia .
docker run --rm --env-file .env -v "$PWD/state:/app/state" -v "$PWD/exports:/app/exports" agente-cronologia
```

O container não possui agendador interno; agende no host. Nenhum agendamento externo foi ativado na entrega.

## Testes e operação

```powershell
python -m unittest discover -s tests -v
python -m cronologia status
```

Código de saída 0 indica término sem erros tratados; 1 indica ao menos uma fonte/extração falhou.
Cada fonte tem transação própria: falha reverte suas alterações, sem apagar outras fontes concluídas.
As reservas de chamadas de IA permanecem registradas mesmo em falhas. Os runs mostram volumes,
arquivos ausentes e coleta vazia. Sem chave, os coletores e exportações funcionam; `extract` falha claramente.
Faça backup de `state` com o agente parado (SQLite pode usar arquivos WAL). Não há conexão Snowflake
configurada nesta versão: banco local e CSV são a entrega funcional, sem presumir suas credenciais.

## Fontes e documentação

- Prefeitura: https://portal-adm.campinas.sp.gov.br/api/busca-noticias?limit=500&page=0
- IBGE: https://servicodados.ibge.gov.br/api/v3/noticias/
- ESPN: https://site.api.espn.com/apis/site/v2/sports/soccer/bra.1/scoreboard?dates=2026&limit=1000
- OpenFootball JSON (CC0): https://github.com/openfootball/football.json
- OpenFootball UEFA: https://github.com/openfootball/champions-league
- Modelo: https://developers.openai.com/api/docs/models/gpt-5-mini
- Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs

Todos os dados são retratos das fontes; não representam todos os acontecimentos do período.
