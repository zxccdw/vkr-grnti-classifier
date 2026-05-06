# grnti-web

Каскадный классификатор научных текстов по ГРНТИ. FastAPI + TEI (BGE-M3) + статический фронт.

## Запуск

```bash
docker compose up -d
open http://localhost:8080
```

Первый запуск скачает BGE-M3 (~1 GB) в docker volume — занимает пару минут.

На macOS с Docker Desktop < 4 GB RAM модель не поднимется. Нужно Settings → Resources → Memory → 8 GB. Либо использовать e5-small для теста:

```bash
TEI_IMAGE=cpu-arm64-latest EMBEDDING_MODEL=intfloat/multilingual-e5-small \
TEI_MAX_BATCH_TOKENS=2048 TEI_MAX_CLIENT_BATCH_SIZE=4 docker compose up -d
```

## API

```bash
curl http://localhost:8080/health

curl -X POST http://localhost:8080/api/v1/classify/full \
  -H "Content-Type: application/json" \
  -d '{"text": "Применение нейросетей для диагностики по МРТ", "top_k": 5}'
```

Эндпоинты: `/classify/l1`, `/classify/l2` (+ `parent_code`), `/classify/l3` (+ `parent_code`), `/classify/full`.

## Переменные окружения

| Переменная | Дефолт | Описание |
|---|---|---|
| `TEI_IMAGE` | `cpu-1.7` | Тег образа TEI. На Apple Silicon: `cpu-arm64-latest` |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | Модель эмбеддингов |
| `TEI_MAX_BATCH_TOKENS` | `16384` | Снизить до `2048` при нехватке RAM |
| `WEB_HOST_PORT` | `8080` | Внешний порт |

## Разработка

```bash
uv sync
uvicorn backend.main:app --reload --port 8000
```

```bash
make lint
make typecheck
```
