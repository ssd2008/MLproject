import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { DocumentItem, HealthResponse } from "./api/types";
import { HealthIndicator } from "./components/HealthIndicator";
import { AssistantPage } from "./pages/AssistantPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { SearchPage } from "./pages/SearchPage";
import { SystemPage } from "./pages/SystemPage";

type Page = "documents" | "assistant" | "search" | "system";

const NAVIGATION: Array<{ id: Page; label: string; caption: string; icon: string }> = [
  { id: "documents", label: "Материалы", caption: "База знаний", icon: "▤" },
  { id: "assistant", label: "Ассистент", caption: "Ответы с цитатами", icon: "✦" },
  { id: "search", label: "Поиск", caption: "Retriever и reranker", icon: "⌕" },
  { id: "system", label: "Система", caption: "Статус компонентов", icon: "◉" },
];

interface ToastState {
  id: number;
  message: string;
  tone: "success" | "error";
}

export default function App() {
  const [page, setPage] = useState<Page>("documents");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [toasts, setToasts] = useState<ToastState[]>([]);

  const refreshDocuments = useCallback(async () => {
    setDocumentsLoading(true);
    setDocumentsError(null);
    try {
      const response = await api.listDocuments({ limit: 500 });
      setDocuments(response.items);
    } catch (caught) {
      setDocumentsError(caught instanceof Error ? caught.message : "Не удалось загрузить документы");
    } finally {
      setDocumentsLoading(false);
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      setHealth(await api.getHealth());
    } catch {
      setHealth(null);
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const notify = useCallback((message: string, tone: "success" | "error" = "success") => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 4500);
  }, []);

  useEffect(() => {
    void refreshDocuments();
    void refreshHealth();
    const interval = window.setInterval(() => void refreshHealth(), 30000);
    return () => window.clearInterval(interval);
  }, [refreshDocuments, refreshHealth]);

  function navigate(nextPage: Page) {
    setPage(nextPage);
    setMobileMenuOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar${mobileMenuOpen ? " sidebar--open" : ""}`}>
        <div className="brand">
          <div className="brand__mark">M</div>
          <div><strong>MedStudy AI</strong><span>Learning assistant</span></div>
        </div>

        <nav className="navigation" aria-label="Основная навигация">
          <span className="navigation__label">Рабочее пространство</span>
          {NAVIGATION.map((item) => (
            <button
              key={item.id}
              type="button"
              className={page === item.id ? "active" : ""}
              onClick={() => navigate(item.id)}
            >
              <span className="navigation__icon">{item.icon}</span>
              <span><strong>{item.label}</strong><small>{item.caption}</small></span>
            </button>
          ))}
        </nav>

        <div className="sidebar__bottom">
          <div className="study-notice">
            <span>i</span>
            <p><strong>Учебный проект</strong>Не используется для диагностики и назначения лечения.</p>
          </div>
          <HealthIndicator health={health} loading={healthLoading} onClick={() => navigate("system")} />
        </div>
      </aside>

      {mobileMenuOpen && <button className="mobile-overlay" type="button" onClick={() => setMobileMenuOpen(false)} aria-label="Закрыть меню" />}

      <main className="main-content">
        <header className="mobile-header">
          <button className="menu-button" type="button" onClick={() => setMobileMenuOpen(true)} aria-label="Открыть меню">☰</button>
          <div className="brand brand--mobile"><div className="brand__mark">M</div><strong>MedStudy AI</strong></div>
          <span className={`mobile-status mobile-status--${health?.status || "unknown"}`} />
        </header>

        <div className="content-container">
          {page === "documents" && (
            <DocumentsPage
              documents={documents}
              loading={documentsLoading}
              error={documentsError}
              refreshDocuments={refreshDocuments}
              notify={notify}
            />
          )}
          {page === "assistant" && <AssistantPage documents={documents} />}
          {page === "search" && <SearchPage documents={documents} />}
          {page === "system" && <SystemPage health={health} loading={healthLoading} refresh={refreshHealth} />}
        </div>
      </main>

      <div className="toast-region" aria-live="polite">
        {toasts.map((toast) => (
          <div className={`toast toast--${toast.tone}`} key={toast.id}>
            <span>{toast.tone === "success" ? "✓" : "!"}</span>
            <p>{toast.message}</p>
            <button type="button" onClick={() => setToasts((current) => current.filter((item) => item.id !== toast.id))}>×</button>
          </div>
        ))}
      </div>
    </div>
  );
}
