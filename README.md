# AI Image Studio — Docker

Plataforma local de edição de imagens: Streamlit, Python/Pillow/OpenCV, rembg U²-Net, Ollama opcional para interpretação de comandos, ComfyUI opcional para workflows generativos (NVIDIA).

**Estado real das funções:** brilho, contraste, saturação, nitidez, fundo sólido, remoção automática de fundo, sombra, texto, ampliação Lanczos, máscara manual com inpainting clássico, histórico e download são implementados. O ComfyUI é um serviço opcional independente: para remover objetos grandes ou gerar cenários com IA é necessário instalar modelos e configurar workflows no ComfyUI; **a interface principal não executa esses workflows automaticamente**. SAM 2, LaMa e Real-ESRGAN **não estão incluídos** nesta versão. Não confunda interpolação Lanczos com super-resolução por IA.

## Início rápido (Windows / VS Code / Docker Desktop)

1. Extraia o ZIP, abra a pasta no VS Code e abra **Terminal > Novo Terminal**.
2. No PowerShell, dentro da pasta do `docker-compose.yml`, rode `Copy-Item .env.example .env`.
3. Edite `.env` e defina uma senha forte em `APP_PASSWORD`.
4. Rode `docker compose up -d --build`.
5. Acesse http://localhost:8501 e digite a senha.
6. Para usar comandos por Ollama: `docker compose exec ollama ollama pull qwen2.5:3b`.
7. Para logs: `docker compose logs -f app`.

Para iniciar o ComfyUI **opcional** em GPU NVIDIA com NVIDIA Container Toolkit: `docker compose --profile generative up -d --build`. Acesse http://localhost:8188 na máquina hospedeira. Instale checkpoints e workflows adequados na interface do ComfyUI; o Dockerfile instala apenas o motor, **não** modelos generativos. O ComfyUI está vinculado a 127.0.0.1 por segurança.

Leia `docs/COMO_SUBIR.md` para instruções detalhadas.
