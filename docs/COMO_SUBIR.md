# Manual completo — AI Image Studio Chat

## 1. O que é

Sistema de edição de imagens local, com **interface única por chat**. O usuário anexa a imagem ao próprio campo de conversa e pede, em português, ajustes tradicionais ou edições generativas. O processamento tradicional funciona sem GPU dedicada; o generativo precisa de GPU NVIDIA e dos perfis opcionais do Docker Compose.

## 2. Requisitos

- Docker Desktop com integração WSL2 no Windows **ou** Docker Engine + Compose no Ubuntu.
- Para operação básica: CPU e 8 a 16 GB de RAM (remoção de fundo pode ser lenta).
- Para perfis generativos `gpu` e `objects`: GPU NVIDIA CUDA compatível; recomendado 16–24 GB ou mais de VRAM, 64 GB de RAM, SSD NVMe com espaço para dezenas de GB de modelos.
- Conexão à internet no primeiro download dos modelos (Ollama, rembg e Hugging Face).
- **Não precisa instalar Python na máquina host.**

A configuração GPU foi preparada para NVIDIA RTX 30/40 no ambiente CUDA 12.4. Para GPUs muito novas (ex.: algumas RTX 50) poderá ser necessário atualizar a imagem do PyTorch/CUDA; as versões dependem dos drivers e arquiteturas de GPU.

## 3. Instalação rápida no Windows (VS Code + PowerShell)

1. Extraia o ZIP.
2. Abra no VS Code **a pasta que contém `docker-compose.yml`**.
3. No menu **Terminal > Novo Terminal**, execute:

```powershell
Copy-Item .env.example .env
```

4. Abra `.env` no explorador do VS Code e troque `APP_PASSWORD=troque-esta-senha` por uma senha forte **sem espaços finais**. Exemplo (escolha sua própria senha):

```env
APP_ADMIN_USER=admin
APP_PASSWORD=COLOQUE_UMA_SENHA_FORTE_AQUI
APP_PORT=8501
OLLAMA_MODEL=qwen2.5:3b
```

5. Salve com `Ctrl + S` e, no terminal, execute:

```powershell
docker compose up -d --build
```

6. Baixe o modelo de interpretação dos comandos:

```powershell
docker compose exec ollama ollama pull qwen2.5:3b
```

7. Abra **http://localhost:8501**. Usuário inicial: `admin`. Senha: a definida no `.env`.
8. No rodapé do chat, clique no **anexo de imagem**, escolha JPG/PNG/WEBP e escreva uma instrução. Também pode anexar primeiro e pedir alterações em mensagens seguintes.

Se o Ollama ainda não estiver pronto, pedidos simples continuam funcionando por regras locais, mas instruções complexas podem solicitar esclarecimento.

## 4. Ativar edição por IA generativa (GPU NVIDIA)

Para `background_scene`, `enhance_ai`, substituição de objetos e outpainting:

```powershell
docker compose --profile gpu up -d --build
```

Para identificar automaticamente objetos descritos em texto (ex.: 'a toalha azul') e produzir máscaras de edição:

```powershell
docker compose --profile gpu --profile objects up -d --build
```

O gerador usa **Stable Diffusion XL com Diffusers** diretamente pelo chat. O serviço de segmentação usa **Grounding DINO + SAM**. O primeiro comando desse tipo baixa modelos grandes da Hugging Face; os downloads ficam guardados em volume Docker. Serviços não expõem porta externa, somente a aplicação web é publicada.

Para executar Ollama com GPU também (opcional; aumenta consumo de VRAM):

```powershell
docker compose -f docker-compose.yml -f docker-compose.nvidia.yml --profile gpu --profile objects up -d --build
```

Verifique o driver com `nvidia-smi` no host. No Windows, deixe a integração WSL2 e o suporte a GPU do Docker funcionando. No Ubuntu, instale o **NVIDIA Container Toolkit** antes de subir perfis com GPU.

## 5. Exemplos de comandos do chat

| Pedido do usuário | Ferramenta |
| --- | --- |
| 'Remova o fundo' | rembg / U²-Net |
| 'Deixe o fundo branco' | rembg + composição |
| 'Troque o fundo por um quarto de hotel' | SDXL text-to-image + rembg |
| 'Aumente o brilho 20% e contraste 10%' | Pillow |
| 'Melhore a foto e corrija as cores' | Pillow + OpenCV |
| 'Remova a toalha azul' | Grounding DINO + SAM + SDXL inpainting |
| 'Troque a toalha azul por outra branca' | Grounding DINO + SAM + SDXL inpainting |
| 'Remova o objeto selecionado rapidamente' | Máscara manual + OpenCV, se configurado fast_mode |
| 'Desfoque o fundo' | rembg + Pillow |
| 'Insira o texto "Linha Premium"' | Pillow |
| 'Amplie duas vezes' | interpolação Lanczos, não IA neural |
| 'Expanda as bordas em 20%' | SDXL inpainting |

**Máscara manual (opcional):** na barra lateral, envie PNG com áreas **brancas** onde a IA pode modificar e **pretas** para preservar. Isso ajuda quando a detecção automática falhar. É um suporte adicional; a maioria dos pedidos pode começar diretamente pelo chat.

**Limite do resultado:** um pedido com vários passos só gera nova versão se todas as etapas forem concluídas; em caso de erro, mantém a versão anterior. Histórico é salvo por usuário em SQLite e imagens em PNG.

## 6. Trocar a senha que você esqueceu

1. Abra o `.env` **na mesma pasta do Compose**. Edite `APP_PASSWORD`.
2. Salve e execute:

```powershell
docker compose up -d --force-recreate app
```

3. Atualize `http://localhost:8501` e faça login com `APP_ADMIN_USER` e a nova senha. A senha do administrador é sincronizada com `.env` ao iniciar o aplicativo.
4. Se ainda não funcionar, execute:

```powershell
docker compose exec app python -c "import os; print('usuário:', os.environ.get('APP_ADMIN_USER')); print('senha configurada:', bool(os.environ.get('APP_PASSWORD')))"
docker compose logs --tail=100 app
```

Não envie sua senha real em prints. **Nunca use `docker compose down -v` se quiser conservar modelos e banco de dados.**

## 7. Comandos de manutenção

```powershell
docker compose ps
docker compose logs --tail=80 app
docker compose logs --tail=80 ollama
docker compose --profile gpu logs --tail=80 generator
docker compose --profile objects logs --tail=80 segmenter
docker compose restart app
docker compose down                  # mantém volumes
```

### GPU sem memória

- Reduza `GEN_MAX_SIDE` para `768` no `.env`.
- Ative `GEN_LOW_VRAM=1` (offload para RAM; mais lento).
- Evite ativar GPU do Ollama durante uma geração grande.
- Recrie: `docker compose --profile gpu --profile objects up -d --force-recreate`.

### Falha no download de modelos

Verifique acesso à Hugging Face, espaço livre, certificados, `HF_TOKEN` se o modelo exigir autorização e logs do serviço. O projeto não acompanha os pesos dos modelos; estes são baixados quando acionados.

### Tela branca ou contêiner reiniciando

Execute `docker compose logs --tail=100 app`. Verifique `.env`, espaço em disco e permissões de `./data`.

### Linux: erro de permissão na pasta `data/`

```bash
mkdir -p data
sudo chown -R 10001:10001 data
```

O contêiner principal roda como UID 10001; pastas de host sem permissão de escrita impedem SQLite e salvamento de PNG.

## 8. Arquivos e dados

- `app/main.py`: chat, anexos, autenticação, versões, download.
- `app/planner.py`: Ollama (resposta estruturada JSON) e regras de contingência.
- `app/processor.py`: todas as operações de edição.
- `app/db.py`: autenticação PBKDF2 e banco SQLite.
- `services/generator/server.py`: API privada de SDXL (texto, imagem, inpainting).
- `services/segmenter/server.py`: API privada de máscaras de objetos por texto.
- `data/studio.sqlite3`: contas, projetos, mensagens e versões.
- `data/files/<uuid>/v0000.png`: imagens originais e versões.

## 9. Segurança e produção

O projeto é uma base funcional e extensível, **não um produto auditado para produção**. Para cinco usuários corporativos, colocar a aplicação atrás de proxy reverso com HTTPS, SSO/identidade, backup, antivírus de uploads, quotas, controle de concorrência/fila de GPU, logs de auditoria e proteção de dados antes de disponibilizar fora da rede de testes. A tela web utiliza senha e contas locais, mas não substitui uma solução de segurança corporativa.

Não expor serviços internos (`ollama`, `generator`, `segmenter`) na internet. Proteger o `.env` e fazer backup de `data/` e dos volumes de modelos se necessário.

**Aviso de fidelidade:** a edição generativa pode inventar texturas, cores, logotipos e características do produto. Toda fotografia comercial deve ser revisada antes de publicar. A troca de cenário com recorte preserva melhor o produto original do que `enhance_ai`.

## 10. Testes

No host com Python e dependências de desenvolvimento instaladas, execute `python -m pytest -q tests`. No desenvolvimento, foram executadas verificações de sintaxe, testes de operações e estrutura do Compose; a execução completa dos modelos depende de Docker, GPU e download dos pesos.

## 11. Inicializadores de conveniência

No Windows (PowerShell, na pasta do projeto), execute `./INICIAR_WINDOWS.ps1`.
No Linux (terminal, na pasta do projeto), execute `./INICIAR_LINUX.sh`.
Se não houver `.env`, o script cria o arquivo a partir do exemplo e pede que você edite a senha antes de prosseguir. Isso **não** apaga o banco ou as imagens existentes.
