# AI Image Studio Chat — Docker

Plataforma local de edição de imagens **com comandos pelo chat**. Anexe uma imagem diretamente à conversa, peça alterações em português e baixe o PNG. Histórico por usuário, login e edição em múltiplas etapas.

## Começar agora

No PowerShell do VS Code, na pasta do projeto:

```powershell
Copy-Item .env.example .env
```

Abra `.env` e **substitua obrigatoriamente `APP_PASSWORD=troque-esta-senha`** por uma senha forte. Em seguida:

```powershell
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:3b
```

Acesse **http://localhost:8501** com usuário `admin` e a senha do `.env`.

Os recursos simples funcionam com o Compose padrão. Para **remoção/substituição automática de objetos e cenários generativos** com GPU NVIDIA:

```powershell
docker compose --profile gpu --profile objects up -d --build
```

Veja [docs/COMO_SUBIR.md](docs/COMO_SUBIR.md) para configuração NVIDIA, exemplos, solução de problemas e troca de senha.

## O que funciona em cada modo

| Recurso | Docker básico | Com perfis GPU + objects |
| --- | --- | --- |
| Chat com imagem anexada e histórico | Sim | Sim |
| Brilho/contraste/cor/nitidez/textos | Sim | Sim |
| Remoção de fundo e fundo de cor | Sim | Sim |
| Redimensionar, girar, cortar, sombra, desfoque | Sim | Sim |
| Interpretação detalhada por Ollama | Sim (modelo após pull) | Sim |
| Fundo gerado por IA | Não | Sim |
| Remover/trocar objetos descritos por texto | Não | Sim |
| Remoção com máscara manual + inpainting | Não | Sim |
| Img2img / melhoria generativa e outpainting | Não | Sim |

**Tecnologia de geração:** SDXL via Diffusers integrado diretamente ao chat (não depende de abrir o ComfyUI). **Modelos não acompanham o ZIP** e são baixados na primeira utilização. Modelos podem exigir aceitação de licença/token. Edits generativos não garantem fidelidade absoluta do produto.

## Organização

```text
ai-image-studio-chat/
├── .env.example
├── docker-compose.yml
├── docker-compose.nvidia.yml
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── db.py
│   ├── planner.py
│   └── processor.py
├── services/
│   ├── generator/{Dockerfile,requirements.txt,server.py}
│   └── segmenter/{Dockerfile,requirements.txt,server.py}
├── docs/COMO_SUBIR.md
├── data/
└── tests/test_project.py
```

Para produção corporativa: precisa HTTPS, SSO/controle de acesso, limites de requisições e fila para GPU, backup e auditoria. Código entregue como base para evolução, sem garantia de compatibilidade de todas as GPUs/modelos.

## Inicialização guiada

Se preferir no Windows, execute `./INICIAR_WINDOWS.ps1` no terminal PowerShell.
Na primeira chamada, o script cria `.env`; edite `APP_PASSWORD` e execute novamente.
No Linux, use `./INICIAR_LINUX.sh`.
