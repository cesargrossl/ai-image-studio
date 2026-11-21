# Como subir o AI Image Studio
docker compose up -d --build
## Requisitos
- Docker Engine com plugin Docker Compose (Linux) ou Docker Desktop (Windows).
- Recomenda-se pelo menos 8 GB de RAM; CPU funciona, mas a remoção de fundo pode ser lenta.
- Internet na primeira execução para baixar as imagens Docker e o modelo U²-Net.
- GPU não é obrigatória neste MVP. O Ollama é um serviço reservado para futura integração do chat inteligente.

## Instalação
1. Extraia `ai-image-studio-docker.zip` e abra o terminal na pasta `ai-image-studio`.
2. Copie `.env.example` para `.env`:
   - Linux: `cp .env.example .env`
   - Windows PowerShell: `Copy-Item .env.example .env`
3. Edite `.env` e configure uma senha forte em `APP_PASSWORD`.
4. Execute `docker compose up -d --build`.
5. Acesse `http://localhost:8501` e faça login com a senha configurada.
6. Para acesso na rede local, abra `http://IP_DO_SERVIDOR:8501` em outro computador e permita a porta 8501 no firewall. Use apenas em rede confiável ou atrás de HTTPS/reverse proxy.

## Como usar
- Envie uma imagem JPG, PNG ou WEBP.
- Digite comandos como `Remova o fundo, coloque fundo branco e adicione sombra`.
- Para texto, use aspas: `Escreva "PROMOÇÃO"`.
- Clique em `Aplicar edição` e depois `Baixar PNG`.

## Comandos úteis
- Logs: `docker compose logs -f app`
- Parar: `docker compose down`
- Reiniciar: `docker compose restart`
- Atualizar após alterar código: `docker compose up -d --build`
- Opcional, baixar modelo de linguagem: `docker compose exec ollama ollama pull qwen2.5:3b`
- Ver serviços: `docker compose ps`

## Limitações
Este MVP é um editor de imagem com interpretação por regras em português, não um editor generativo com FLUX/Stable Diffusion. O serviço Ollama está disponível no Compose, mas ainda não é usado pelo app. A sombra é simples e o texto é aplicado na parte superior. Não há contas individuais, histórico ou fila multiusuário. Para produção com cinco usuários e 100 imagens/dia, implementar autenticação individual, proxy HTTPS, fila de processamento e limites de recursos.

## Segurança
Não publique a porta 8501 diretamente na internet. Defina uma senha forte. Imagens não são enviadas a APIs pagas pelo aplicativo; a remoção de fundo roda localmente após baixar o modelo.
