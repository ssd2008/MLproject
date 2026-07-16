import type { HealthResponse } from "../api/types";
import { Button, EmptyState, Spinner, Tag } from "../components/ui";

const COMPONENT_LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  qdrant: "Qdrant",
  embedding: "Embedding",
  reranker: "Reranker",
  answer: "Answer backend",
};

export function SystemPage({
  health,
  loading,
  refresh,
}: {
  health: HealthResponse | null;
  loading: boolean;
  refresh: () => Promise<void>;
}) {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <span className="eyebrow">Diagnostics</span>
          <h1>Состояние системы</h1>
          <p>Проверка API, баз данных и активных ML-компонентов.</p>
        </div>
        <Button variant="secondary" loading={loading} onClick={() => void refresh()}>Обновить статус</Button>
      </section>

      {!health && loading ? (
        <div className="panel center-loader center-loader--large"><Spinner /></div>
      ) : !health ? (
        <div className="panel"><EmptyState icon="!" title="API недоступен" text="Проверьте, что Docker Compose запущен и backend слушает порт 8000." /></div>
      ) : (
        <>
          <section className={`system-hero system-hero--${health.status}`}>
            <div className="system-hero__icon">{health.status === "ok" ? "✓" : "!"}</div>
            <div>
              <span>{health.service}</span>
              <h2>{health.status === "ok" ? "Все компоненты работают" : "Система работает с ограничениями"}</h2>
              <p>Версия API: {health.version}</p>
            </div>
            <Tag tone={health.status === "ok" ? "success" : "danger"}>{health.status.toUpperCase()}</Tag>
          </section>

          <section className="component-grid">
            {Object.entries(health.components).map(([name, component]) => (
              <article className="component-card" key={name}>
                <div className="component-card__header">
                  <span className={`component-dot component-dot--${component.status}`} />
                  <strong>{COMPONENT_LABELS[name] || name}</strong>
                  <Tag tone={component.status === "ok" ? "success" : component.status === "disabled" ? "neutral" : "danger"}>{component.status}</Tag>
                </div>
                <p>{component.detail || (component.status === "ok" ? "Подключение установлено" : "Нет дополнительной информации")}</p>
              </article>
            ))}
          </section>

          <div className="split-layout system-details">
            <section className="panel">
              <div className="panel-heading"><div><span className="eyebrow">Pipeline</span><h2>Текущая архитектура</h2></div></div>
              <div className="pipeline">
                {["React frontend", "FastAPI", "Chunking", health.components.embedding?.detail || "Embeddings", "Qdrant", health.components.reranker?.detail || "Reranker", health.components.answer?.detail || "Answer"].map((step, index, array) => (
                  <div className="pipeline__item" key={`${step}-${index}`}>
                    <span>{index + 1}</span><strong>{step}</strong>{index < array.length - 1 && <i>→</i>}
                  </div>
                ))}
              </div>
            </section>

            <section className="panel quick-links">
              <div className="panel-heading"><div><span className="eyebrow">Developer tools</span><h2>Инструменты</h2></div></div>
              <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer"><span>API</span><div><strong>Swagger UI</strong><small>Просмотр и ручной вызов endpoints</small></div><b>↗</b></a>
              <a href="http://127.0.0.1:6333/dashboard" target="_blank" rel="noreferrer"><span>Q</span><div><strong>Qdrant Dashboard</strong><small>Коллекции, points и payload</small></div><b>↗</b></a>
              <a href="http://127.0.0.1:8000/api/v1/health" target="_blank" rel="noreferrer"><span>H</span><div><strong>Health JSON</strong><small>Исходный ответ диагностики</small></div><b>↗</b></a>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
