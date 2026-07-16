import type { HealthResponse } from "../api/types";
import { Spinner } from "./ui";

export function HealthIndicator({
  health,
  loading,
  onClick,
}: {
  health: HealthResponse | null;
  loading: boolean;
  onClick: () => void;
}) {
  const status = health?.status ?? "unknown";
  return (
    <button className="health-indicator" type="button" onClick={onClick}>
      {loading ? (
        <Spinner small />
      ) : (
        <span className={`health-indicator__dot health-indicator__dot--${status}`} />
      )}
      <span>
        <strong>
          {status === "ok"
            ? "Система работает"
            : status === "degraded"
              ? "Есть ошибки"
              : "Проверка системы"}
        </strong>
        <small>{health ? `API ${health.version}` : "Статус компонентов"}</small>
      </span>
    </button>
  );
}
