# Arquivos de ingestão diária

Todo dia útil, exporte do Instar (usuário `eptv-br-61`) os **3 arquivos abaixo**, sempre referentes ao **dia anterior (D-1)**. Solte-os nesta pasta (`promo_semanal/entrada/`) e rode no VS Code a tarefa **Atualizar base EPTV** (`Ctrl+Shift+B`).

| # | Arquivo | Template do Instar | O que alimenta no painel |
|---|---|---|---|
| 1 | PROGRAMAS | `INGESTAO DIARIA PROGRAMAS.ist` | Horários e audiência de cada programa: base diária, BASE_HISTORICA e BASE_SEMANAL |
| 2 | FAIXAS (minuto a minuto) | `INGESTAO DIARIA FAIXAS.ist` | Curva minuto a minuto, mapa "Onde chamar", Rat% e Shr% TLE dos dias novos |
| 3 | PERFIL | `PERFIL_TEMP.ist` | Perfil do público, afinidade, ranking "Onde chamar" e concorrência |

**O nome do arquivo não importa.** O sistema reconhece cada arquivo pelas abas e pela primeira linha, então "INGESTAO DIARIA PROGRAMAS (7).xlsx" funciona. O que **não pode mudar** é o que está descrito nos cartões técnicos abaixo.

---

## 1. PROGRAMAS · `INGESTAO DIARIA PROGRAMAS.ist`

### Cartão técnico
| Campo | Valor |
|---|---|
| Base | Brasil - 15 mercados (Dispositivo medido e reportado: TV) (55) |
| Datas | D-1 (um dia; vários dias também funcionam) |
| Targets | Total Domicílios |
| Praças | Grande Campinas |
| Emissoras | GLOBO |
| Variáveis | Rat#, Rat%, Shr% |
| Atividades | Live (Consolidado também é aceito; veja a nota) |
| Programs filter | Set 1 |
| Universo | Total Domicílios: 876 mil (243 casos) |

### Estrutura esperada
- Aba **`Programas`**:
  - linha 1 com o título, contendo a base: `Programas (Total Domicílios|Grande Campinas|Live)`;
  - linha 2 com o cabeçalho: `Nome Programa · Sequencial · Emissora · Data · Hora Início · Hora Fim · Rat# · Rat% · Shr%`;
  - linha 3 com o `Total`, que é descartado.
- Abas `Crosstab` e `Cartão Técnico` podem vir junto e são ignoradas.
- Formatos: data `dd/mm/aaaa`; horas no padrão de grade (`25:30:00` = 01:30 da madrugada, ainda no mesmo dia de TV).

> **Live × Consolidado:** um dia que entrou como Live aparece como **prévia** no painel. Quando o mesmo dia for exportado depois com **Atividades = Consolidado** e ingerido, ele substitui o Live automaticamente. O contrário não acontece: um Live nunca sobrescreve um Consolidado.

---

## 2. FAIXAS · `INGESTAO DIARIA FAIXAS.ist`

### Cartão técnico
| Campo | Valor |
|---|---|
| Base | Brasil - 15 mercados (Dispositivo medido e reportado: TV) (55) |
| Datas | D-1 |
| Targets | Total Domicílios |
| Praças | Grande Campinas |
| Emissoras | GLOBO |
| Variáveis | Rat#, Rat%, Shr%, Shr% [Required \| Total Ligados Especial] |
| Atividades | **Consolidado** |
| Faixa | Dia inteiro, de 1 em 1 minuto, 06:00 → 29:59 (1.440 linhas por dia) |
| Programs filter | Set 1 |
| Universo | Total Domicílios: 876 mil (243 casos) |

### Estrutura esperada
- Aba **`Faixas Horárias`**:
  - linha 1 com o título: `Faixas Horárias (Total Domicílios|Grande Campinas|Consolidado)`;
  - linha 2 com o cabeçalho: `Data · Hora Início · Duração · Emissora · Nome · Rat# · Rat% · Shr%`;
  - linha 3 com o `Total`, que é descartado.
- O Shr% do minuto precisa ser o **Total Ligados Especial**, o mesmo da BASE_HISTORICA. É dele que sai o Shr% dos dias novos.
- Se o export trouxer também a aba `Programas` (como no arquivo histórico grande), ela é lida junto.

> Por que este arquivo é importante: quando o dia ainda não está na BASE_HISTORICA, o **Rat% e o Shr% de cada programa saem deste minuto a minuto** (média dos minutos do programa). Isso bate com o Crosstab do Instar em 90% dos programas com diferença de até 0,02 pt. Sem este arquivo, o sistema usa o Rat% do PROGRAMAS, que é menos preciso.

---

## 3. PERFIL · `PERFIL_TEMP.ist`

### Cartão técnico
| Campo | Valor |
|---|---|
| Base | Brasil - 15 mercados (Dispositivo medido e reportado: TV) (55) |
| Datas | D-1 (o arquivo atual cobre de 01/08/2026 a 07/10/2026) |
| Praças | Grande Campinas |
| Emissoras | GLOBO, RECORD, SBT, TV BAND |
| Variáveis | Rat# |
| Atividades | Consolidado |
| Programs filter | Set 1 |

### Targets (os nomes precisam ser exatamente estes)
| Target no export | Definição no Instar | Universo (mil) | Casos |
|---|---|---|---|
| AB1 | Classe Social Detalhada › AB1 | 302 | 94 |
| B2 | Classe Social Detalhada › B2 | 677 | 209 |
| C1 | Classe Social Aberta › C1 | 609 | 185 |
| C2 | Classe Social Aberta › C2 | 488 | 138 |
| DE | Classe Social › DE | 152 | 57 |
| 4-11 anos | Idades 2015 › 4-11 anos | 232 | 74 |
| 12-17 anos | Idades 2015 › 12-17 anos | 168 | 61 |
| 18-24 anos | Idades 2015 › 18-24 anos | 202 | 70 |
| 25-34 anos | Idades 2015 › 25-34 anos | 358 | 80 |
| 35-49 anos | Idades 2015 › 35-49 anos | 580 | 176 |
| 50-59 anos | Idades 2015 › 50-59 anos | 280 | 82 |
| 60+ anos | Idades 2015 › 60+ anos | 406 | 140 |
| HOMENS | Sexo › Masculino | 1.094 | 338 |
| MULHERES | Sexo › Feminino | 1.134 | 345 |

O painel agrupa os públicos pelo nome:
- `AB1, B2, C1, C2, DE` → **Classe**;
- qualquer nome com "anos" → **Idade**;
- `HOMENS, MULHERES` → **Sexo**.

Renomear um target (por exemplo, "Homens" no lugar de "HOMENS") tira esse público do agrupamento.

### Estrutura esperada
- Aba **`Programas`**:
  - linha 1 com o título: `Programas (Grande Campinas|Consolidado)`;
  - linha 2 começando com **`Variáveis >>`** e `Rat#` sobre cada target. É essa linha que identifica o arquivo como PERFIL;
  - linha 3 com o cabeçalho: `Nome Programa · Emissora · Data · Hora Início · Hora Fim · AB1 · … · MULHERES`;
  - linha 4 com o `Total`, que é descartado.

> Atenção à amostra: DE (57 casos), 12-17 (61), 18-24 (70) e 4-11 (74) têm poucos casos. Em um dia isolado esses públicos oscilam muito; leia o perfil no período de semanas, como o painel já faz.

---

## Outros arquivos aceitos (eventuais)

| Arquivo | Quando enviar | Como é tratado |
|---|---|---|
| `Ocorrencias_agente.csv` | **Automático**: o agente de cronologia grava aqui a cada execução | Substitui a tabela inteira de eventos (feriados, datas, acontecimentos, futebol brasileiro) |
| `BASE_HISTORICA_*.xlsx` (aba `Crosstab`: Data · Nome Programa · Rat% · Shr%) | Só para corrigir dias com a base oficial | Vira **referência** e prevalece sobre os dias derivados do Instar |

Arquivos ignorados de propósito: `BASE_SEMANAL` (é recalculada), `Cronologia_*.xlsx` e `Calendario_*.csv` (nenhuma tela usa).

## O que acontece ao rodar "Atualizar base EPTV"
1. Cada arquivo tem o tipo e a base (Live/Consolidado) identificados pelo conteúdo.
2. Os dados entram na base única **dia a dia, substituindo o dia inteiro**. Consolidado vence Live, e a BASE_HISTORICA oficial vence o que foi derivado.
3. Um arquivo com conteúdo idêntico a outro já processado é pulado. Para reprocessar, rode `python ingestao/atualizar.py --forcar`.
4. A BASE_HISTORICA e a BASE_SEMANAL são regravadas na pasta TERÇA-FEIRAS, com backup em `promo_semanal/backup/`.
5. Os arquivos vão para `entrada/processados/AAAA-MM-DD/`.
6. No fim, o terminal mostra a cobertura das tabelas e os dias que ainda estão só em Live.

## Checklist rápido do dia
- [ ] PROGRAMAS de D-1 (Live ou Consolidado)
- [ ] FAIXAS de D-1 (Consolidado, 1 minuto, 06:00–29:59)
- [ ] PERFIL de D-1 (4 emissoras, 14 targets, Rat#)
- [ ] Opcional: PROGRAMAS Consolidado de dias que ficaram em prévia
- [ ] `Ctrl+Shift+B` → conferir no terminal "dia(s) gravado(s)"

> **Uso dos dados:** o Cartão Técnico de todos os exports diz que os dados são de uso restrito e "não podem ser … utilizados como insumo para sistemas internos … sem consentimento e expressa anuência do IBOPE". Confirme com a área de Pesquisa antes de ampliar o uso do painel.
