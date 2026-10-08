# Validação da entrega — 08/10/2026

- 27 testes automatizados passaram em Python 3.12/Linux.
- Carga inicial real: 39.192 inserções, calendário com 1.096 dias.
- Segunda importação: 39.192 registros inalterados, nenhuma duplicação.
- Consulta HTTP real validada nas quatro fontes: Campinas, IBGE, ESPN e OpenFootball.
- Atualização integrada validada para Campinas, IBGE e Brasileirão Série A.
- Amostra integrada após atualização: 39.199 registros; a diferença em relação à carga inicial
  corresponde a novos IDs retornados pelas fontes durante a validação. A base enviada no ZIP
  continua sendo o retrato original de 39.192 registros, com a coleta incremental pronta para rodar.
- IBGE: formato dos parâmetros MM-DD-AAAA confirmado; resposta DD/MM/AAAA.
- Bloqueio de execução simultânea observado; segunda execução no mesmo estado foi rejeitada.
- Ausência de OPENAI_API_KEY produziu erro explícito, sem chamada ao modelo.
- Integração Responses API testada com respostas simuladas: JSON estruturado, recusa e resposta incompleta.
- Cache, limite diário persistente, revisão, evidência literal, datas inválidas, fuso cruzando meia-noite,
  placar futuro vazio, rollback e preservação de histórico em arquivo vazio foram verificados.

**Limites da validação:** não houve chamada real ao GPT mini, porque não há chave OpenAI configurada
no ambiente desta entrega. Não houve teste em Windows, ativação de tarefa agendada, deployment nem
conexão com Snowflake. O pacote inclui comandos e scripts para execução/agendamento local.
