# AI Image Studio - Windows PowerShell
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'Docker não encontrado. Instale/inicie o Docker Desktop.'
    exit 1
}
if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Arquivo .env criado. Abra-o no VS Code, altere APP_PASSWORD e salve.' -ForegroundColor Yellow
    exit 0
}
$pwdLine = Get-Content '.env' | Where-Object { $_ -match '^APP_PASSWORD=' } | Select-Object -First 1
if (-not $pwdLine -or $pwdLine -eq 'APP_PASSWORD=troque-esta-senha' -or $pwdLine -eq 'APP_PASSWORD=') {
    Write-Error 'Edite APP_PASSWORD no arquivo .env e execute este script novamente.'
    exit 1
}
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Falha ao iniciar os serviços Docker.' }
Write-Host 'Aplicação: http://localhost:8501' -ForegroundColor Green
Write-Host 'Baixar modelo Ollama (primeira vez): docker compose exec ollama ollama pull qwen2.5:3b'
Write-Host 'Ativar IA de objetos/cenários com NVIDIA: docker compose --profile gpu --profile objects up -d --build'
