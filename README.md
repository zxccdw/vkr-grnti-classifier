# grnti-web

Обозреватель и редактор онтологии ГРНТИ с LLM-описаниями на рёбрах + каскадный классификатор по эмбеддингам.

## Запуск

```bash
cp .env.example .env
# заполнить токены провайдеров (см. ниже)
docker compose up -d
open http://localhost:8080/browse
```

При первом запуске скачается модель эмбеддингов в docker volume (e5-small ~400 MB, BGE-M3 ~1 GB).

## Что заполнить в .env

| Что | Зачем |
|---|---|
| `AUTH_USERNAME`, `AUTH_PASSWORD` | HTTP Basic Auth (логин/пароль). Если пароль пустой - защита отключена |
| `GIGACHAT_BASE_URL`, `GIGACHAT_TOKEN` | OpenAI-совместимый прокси для GigaChat. Пусто = выключено |
| `YAGPT_BASE_URL`, `YAGPT_TOKEN` | то же для YandexGPT |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` (production) или `intfloat/multilingual-e5-small` (быстрее, для теста) |
| `TEI_IMAGE` | `cpu-1.7` или `cpu-arm64-latest` на Apple Silicon |
| `TEI_MAX_BATCH_TOKENS` | `16384` дефолт; `2048` если мало RAM |
| `WEB_HOST_PORT` | внешний порт |

Backend ходит к LLM по протоколу OpenAI Chat Completions (`POST {base_url}/chat/completions` с `Authorization: Bearer {token}`). Нативные API Сбера/Яндекса этому формату не соответствуют — нужен прокси (Eliza, LiteLLM, vLLM).

Если оба токена пустые, узлы и связи создаются без описаний (`descriptions = []`); потом догоните через кнопку **«Догнать описания»** когда токен появится.

## Эндпоинты

- `GET /browse` — UI обозревателя
- `POST /api/v1/classify/{l1,l2,l3,full}` — классификация текста
- `POST /api/v1/nodes` / `/nodes/with-edge` — создание узла
- `POST /api/v1/edges` — привязка существующего узла под нового родителя
- `POST /api/v1/backfill` — догнать LLM-описания
- `POST /api/v1/merge-duplicates` — схлопнуть узлы по `(label, суффикс кода)`
- `GET /api/v1/export/ontology.json` / `POST /api/v1/import/ontology` — выгрузка/загрузка JSON
- `GET /api/v1/search?q=...` — поиск по label/code

OpenAPI: `http://localhost:8080/docs`.

## Подмена промпта без пересборки

```yaml
services:
  web:
    volumes:
      - ./my_prompt.txt:/app/backend/infrastructure/llm/prompts/v8_project.txt:ro
```

## Деплой в Yandex Serverless Containers

### Особенности serverless-версии

- **Холодный старт:** контейнер "просыпается" при первом запросе после простоя, загрузка занимает 3-5 секунд
- **Доступ:** контейнер можно скрыть (`deny-unauthenticated-invoke`) или открыть (`allow-unauthenticated-invoke`) в публичный доступ
- **Авторизация:** простая HTTP Basic Auth (логин + пароль из `.env`)
- **Лимит выполнения:** платформа убивает запрос через 300 секунд. Если генерация LLM-описаний для большого дерева не успела — используйте кнопку **«Догнать описания»** в UI
- **Классификация:** используется OpenAI-совместимый embedder (модель из `.env`)
- **Генерация описаний:**
  - GigaChat — работает на личном ключе бесплатно (возможно, понадобится кафедральный аккаунт)
  - YaGPT — через прокси `https://polza.ai/api/v1`
- **Хранение:** дерево онтологии и предвычисленные эмбеддинги лежат в S3 (настройки `S3_*` в `.env`)
- **Деплой:** через `./deploy.sh` — нужно один раз получить ID ресурсов (см. ниже). Скрипт читает `.env` и циклом перечисляет все переменные в `--environment` при создании ревизии, т.к. Yandex Serverless не поддерживает `.env` файлы

### Подготовка (один раз)

Узнать ID ресурсов:
```bash
yc container registry list          # YC_REGISTRY_ID
yc serverless container list        # YC_CONTAINER_ID
yc iam service-account list         # YC_SA_ID
```

Добавить в `~/.zshrc`:
```bash
export YC_REGISTRY_ID=<id реестра>
export YC_CONTAINER_ID=<id контейнера>
export YC_SA_ID=<id сервисного аккаунта>
export YC_CONTAINER_NAME=grnti-web
```

Заполнить в `.env` все токены (`AUTH_PASSWORD`, `YAGPT_TOKEN`, `GIGACHAT_CREDENTIALS`, `S3_*`).

### Задеплоить

```bash
./deploy.sh
```

Соберёт образ под `linux/amd64`, запушит в реестр, создаст новую ревизию.

### Аутентификация

Приложение защищено HTTP Basic Auth (stateless, работает в serverless).

При первом заходе браузер покажет модальное окно с запросом логина/пароля. Используйте credentials из `.env`:
- Логин: `admin` (или значение `AUTH_USERNAME`)
- Пароль: значение `AUTH_PASSWORD`

Чтобы отключить защиту, оставьте `AUTH_PASSWORD` пустым в `.env`.

### Открыть / закрыть доступ

```bash
# открыть (публичный URL, но защищен паролем из AUTH_PASSWORD)
yc serverless container allow-unauthenticated-invoke --name grnti-web

# закрыть
yc serverless container deny-unauthenticated-invoke --name grnti-web
```

### URL и логи

```bash
yc serverless container get grnti-web --format json | jq -r .url
yc logging read --folder-id <folder-id> --follow
```

> Serverless не тарифицируется в простое — платишь только за запросы.

## Разработка

```bash
uv sync
uvicorn backend.main:app --reload --port 8000

make lint
make typecheck
.venv/bin/python -m pytest tests/ -q
```
