import type { DocumentStatus, SourceType } from "./api/types";

export const SOURCE_LABELS: Record<SourceType, string> = {
  pdf: "PDF",
  url: "URL",
  text: "Текст",
  video: "Видео",
};

export const STATUS_LABELS: Record<DocumentStatus, string> = {
  uploaded: "Загружен",
  processing: "Индексируется",
  ready: "Готов",
  failed: "Ошибка",
};

export function formatDate(value: string | null | undefined, includeTime = false): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

export function formatBytes(value: number | null): string {
  if (value === null) return "—";
  if (value < 1024) return `${value} Б`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} КБ`;
  return `${(value / 1024 ** 2).toFixed(1)} МБ`;
}

export function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(3);
}

export function formatTimecode(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const totalSeconds = Math.max(0, Math.floor(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function sourceLocationLabel(
  pageStart: number | null,
  pageEnd: number | null,
  timeStart: number | null,
  timeEnd: number | null,
): string {
  if (timeStart !== null) {
    const start = formatTimecode(timeStart);
    const end = timeEnd !== null ? formatTimecode(timeEnd) : start;
    return start === end ? `Тайм-код ${start}` : `Тайм-код ${start}–${end}`;
  }
  if (!pageStart) return "Без номера страницы";
  if (!pageEnd || pageStart === pageEnd) return `Страница ${pageStart}`;
  return `Страницы ${pageStart}–${pageEnd}`;
}

export function cleanOptional(value: string): string | undefined {
  const normalized = value.trim();
  return normalized || undefined;
}

export function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
