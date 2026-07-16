import type { DocumentStatus, SourceType } from "./api/types";

export const SOURCE_LABELS: Record<SourceType, string> = {
  pdf: "PDF",
  url: "URL",
  text: "Текст",
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

export function pageLabel(start: number | null, end: number | null): string {
  if (!start) return "Без номера страницы";
  if (!end || start === end) return `Страница ${start}`;
  return `Страницы ${start}–${end}`;
}

export function cleanOptional(value: string): string | undefined {
  const normalized = value.trim();
  return normalized || undefined;
}

export function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
