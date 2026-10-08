# Painel Promo · Produtos Locais EPTV

Painel semanal (semana de TV de segunda a domingo) para orientar o time de Promo a partir dos 8 produtos locais:
BOM DIA CIA, JORNAL EPTV 1, GLOBO ESPORTE, JORNAL EPTV 2, EP AGRO, TERRA DA GENTE, MAIS CAMINHOS e ESPIA SÓ.

O painel **só lê**. Tudo o que é ingestão roda pelo VS Code.

## Rotina diária
1. Baixe do Instar os arquivos do dia: PROGRAMAS, FAIXAS (minuto a minuto) e PERFIL. Os templates e o cartão técnico de cada um estão em [entrada/README.md](entrada/README.md).
2. Solte os arquivos em `promo_semanal/entrada/`.
3. No VS Code: `Ctrl+Shift+B` → **Atualizar tudo (cronologia + base EPTV)**. Primeiro o agente de cronologia (`../agente_cronologia`) atualiza os jogos e entrega `Ocorrencias_agente.csv` em `entrada/`. Depois a ingestão do painel:
   - detecta o tipo de cada arquivo pelo conteúdo (o nome do arquivo não importa);
   - grava na base única (`base/eptv_promo.duckdb`), sempre substituindo o dia inteiro. O Consolidado substitui o Live, e o Live nunca sobrescreve o Consolidado;
   - cria as linhas novas no padrão da BASE_HISTORICA e regrava `BASE_HISTORICA_V1_RF.xlsx` e `BASE_SEMANAL_V1_RF.xlsx` na pasta TERÇA-FEIRAS, guardando backup em `backup/` (ficam os 10 mais recentes);
   - move os arquivos para `entrada/processados/AAAA-MM-DD/`. Arquivos com o mesmo conteúdo de um já processado são ignorados.

Se o painel estiver aberto, a atualização funciona normalmente, porque ele só abre a base para ler e fecha em seguida.

## Rotina semanal (Promo)
**Abrir painel Promo** (tarefa do VS Code) → http://localhost:8502
- **Semana**: classificação de cada produto, com os comparativos da semana anterior, da média de 4 semanas e do ano anterior.
- **Produto em detalhe**: série de 52 semanas, minuto a minuto, herança e retenção.
- **Onde chamar**: blocos de maior audiência antes de cada exibição e programas que mais entregam o público do produto.
- **Perfil e concorrência**: composição do público, afinidade e emissoras no mesmo horário.
- **Próxima semana**: feriados, datas e futebol, com o comportamento dos produtos em datas parecidas.
- **Briefing**: Excel e HTML para enviar ao time.

## Regras de cálculo
| Item | Regra |
|---|---|
| Rat%/Shr% semanal | Média simples dos dias com exibição. Confere com a BASE_SEMANAL original em 100% dos casos |
| Exib habituais | Mediana das exibições semanais do programa, com arredondamento bancário (99,97% de acerto) |
| Comparável | Semana completa (7 dias) e exibições ≥ 60% das habituais |
| Linha diária nova (dia sem BASE_HISTORICA) | Com minuto a minuto: Rat% = média dos minutos do programa e Shr% TLE = Rat médio ÷ TLE médio (90% dos programas a ≤ 0,02 pt do Crosstab). Sem minuto a minuto: média das exibições ponderada pela duração |
| Classificação | Reforçar ou Aproveitar quando Δ contra a média de 4 semanas ≥ 10% **e** ≥ 0,5 pt (limiares ajustáveis na barra lateral). Atípico quando a semana não é comparável, o horário foi deslocado ou houve feriado/evento nacional |

Os nomes de programa de cada produto ficam em `config/produtos.csv`. Edite esse arquivo quando houver troca de nome na grade.
Os times destacados no futebol ficam em `config/times_regiao.csv`.

## Primeira instalação / reconstrução
```
pip install -r requirements.txt
python ingestao/carga_inicial.py --recriar     # lê os arquivos da pasta TERÇA-FEIRAS (~30 s)
python -m pytest -q tests
```

## Atenção
- O Cartão Técnico do IBOPE restringe o uso dos dados em sistemas internos sem anuência. Confirme com a área de Pesquisa.
- Não há grade futura. A agenda mostra os produtos que costumam ir ao ar em cada dia.
- O PERFIL só tem histórico a partir de 01/08/2026.
