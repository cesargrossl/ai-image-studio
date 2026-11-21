# Manual de instalação — AI Image Studio

## Pré-requisitos

- Windows 10/11 com Docker Desktop + WSL2, ou Linux com Docker Engine e Docker Compose.
- Recomenda-se 16 GB de RAM para funções básicas e 32–64 GB para uso mais intenso.
- GPU NVIDIA e NVIDIA Container Toolkit são **opcionais** para a aplicação principal e necessários para o perfil `generative` definido neste projeto.
- A primeira remoção de fundo baixa um modelo para o volume `rembg_models`, exigindo internet inicialmente.

## 1. Abrir projeto no VS Code

Extraia o ZIP. Abra a pasta `ai-image-studio-completo` no VS Code. Abra **Terminal > Novo Terminal** e confirme que `docker-compose.yml` aparece ao executar `dir`.

## 2. Criar .env (PowerShell)

```powershell
Copy-Item .env.example .env
```

Abra `.env` e substitua `APP_PASSWORD=troque-esta-senha-forte` por uma senha longa e exclusiva, sem compartilhar esse arquivo. A senha é necessária para o aplicativo iniciar. No Linux, use `cp .env.example .env`.

## 3. Subir serviços principais

```powershell
docker compose up -d --build
docker compose ps
```

Abra **http://localhost:8501** e faça login. O serviço `ollama` inicia, mas o modelo de linguagem ainda não é baixado.

## 4. Baixar modelo para interpretar comandos (opcional)

```powershell
docker compose exec ollama ollama pull qwen2.5:3b
```

Na aba **Comandos**, escreva uma instrução e clique em **Interpretar com Ollama**. A IA propõe uma operação; confirme antes de aplicar. Instruções complexas não são automaticamente executadas.

## 5. Editar imagens

1. Envie JPG, PNG ou WEBP (até 30 MB e 24 megapixels).
2. Use **Ajustes** para brilho, contraste, saturação e nitidez.
3. Use **Fundo** para remover o fundo com U²-Net, aplicar uma cor ou sombra.
4. Use **Remover objeto** para pintar a área e aplicar inpainting clássico. Para objetos grandes o resultado pode ficar ruim.
5. Use **Texto** e **Ampliar** conforme necessário.
6. Clique **Salvar edição no histórico** e **Baixar imagem PNG**.

## 6. ComfyUI opcional — edição generativa avançada

Somente em computador com GPU NVIDIA e drivers compatíveis, configure o suporte a GPU do Docker (NVIDIA Container Toolkit no Linux; Docker Desktop com backend WSL2 e drivers NVIDIA no Windows).

```powershell
docker compose --profile generative up -d --build
```

Acesse **http://localhost:8188**. Instale manualmente checkpoints de modelos compatíveis com sua VRAM, configure workflows de inpainting/img2img e confira licenças de uso. **Esta versão não conecta automaticamente o chat Streamlit aos workflows do ComfyUI.** Modelos de alta qualidade podem exigir 16–24 GB de VRAM ou mais, dependendo do workflow.

O ComfyUI está exposto apenas em `127.0.0.1` no host. Não o exponha diretamente à internet.

## 7. Logs e manutenção

```powershell
docker compose ps
docker compose logs --tail=100 app
docker compose logs --tail=100 ollama
docker compose restart app
docker compose down
```

Para atualizar o código:

```powershell
docker compose up -d --build
```

**Não execute `docker compose down -v`**, pois isso apaga os volumes dos modelos. As imagens originais e editadas ficam em `storage/`.

## 8. Acesso em rede e segurança

Para testes na rede local, acesse `http://IP_DO_SERVIDOR:8501` e libere apenas a porta 8501 no firewall para a sub-rede desejada. A senha é **compartilhada**, não existem contas individuais. Não exponha a aplicação diretamente à internet. Para produção, implemente HTTPS por proxy reverso, autenticação individual, controle de acesso, limites de uso, backups, atualização e varredura de uploads. Os arquivos de imagens são armazenados no host sem criptografia específica do aplicativo.

## 9. Solução de problemas

- **Página branca:** `docker compose logs --tail=100 app`; tente janela anônima.
- **Não abre:** confira `docker compose ps`, porta 8501 e firewall.
- **Senha não configurada:** verifique `.env` e rode `docker compose up -d --force-recreate`.
- **Ollama falha:** baixe o modelo com `docker compose exec ollama ollama pull qwen2.5:3b`.
- **Remoção de fundo lenta:** primeiro uso baixa o modelo; CPU pode ser lenta.
- **GPU não detectada:** confirme drivers e NVIDIA Container Toolkit antes de iniciar o perfil generative.
