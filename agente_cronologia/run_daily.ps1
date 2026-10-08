# Rotina diária do agente de cronologia (Agendador do Windows ou tarefa do VS Code).
# Atualiza jogos da ESPN, exporta e entrega ocorrencias.csv em promo_semanal/entrada/.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
if (-not (Test-Path "state\chronology.sqlite")) {
    python -m cronologia init
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
# Fontes vêm de config/settings.json ("sources"). A extração por GPT só faz sentido
# com fontes de notícias (campinas/ibge) e OPENAI_API_KEY no .env; para ativar, use:
#   python -m cronologia update --with-ai
python -m cronologia update
exit $LASTEXITCODE
