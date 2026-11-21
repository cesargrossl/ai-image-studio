#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo 'Criado .env. Edite APP_PASSWORD e execute novamente.'
  exit 0
fi
if grep -Eq '^APP_PASSWORD=(troque-esta-senha)?$' .env; then
  echo 'Defina APP_PASSWORD no arquivo .env antes de iniciar.' >&2
  exit 1
fi
docker compose up -d --build
echo 'Acesse http://localhost:8501'
echo 'Na primeira vez: docker compose exec ollama ollama pull qwen2.5:3b'
