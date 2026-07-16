# Frontend

React + Vite + TypeScript интерфейс для Medical Learning Assistant.

## Локальная разработка

Backend должен быть доступен на `http://127.0.0.1:8000`.

```bash
cd frontend
npm install
npm run dev
```

Откройте `http://127.0.0.1:5173`. Vite проксирует `/api` в FastAPI.

## Production-сборка

```bash
npm run build
```

В составе проекта frontend запускается через Docker Compose и доступен на
`http://127.0.0.1:3000`.
