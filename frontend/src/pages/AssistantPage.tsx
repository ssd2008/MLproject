import { FormEvent, useState } from "react";
import { api } from "../api/client";
import type { AnswerResponse, DocumentItem, ResponseStyle } from "../api/types";
import { DocumentPicker } from "../components/DocumentPicker";
import { Button, EmptyState, ErrorBanner, ScoreBar, Spinner, Tag } from "../components/ui";
import { formatScore, pageLabel } from "../utils";

const STYLE_LABELS: Record<ResponseStyle, string> = {
  brief: "Кратко",
  detailed: "Подробно",
  study_notes: "Конспект",
};

export function AssistantPage({ documents }: { documents: DocumentItem[] }) {
  const [query, setQuery] = useState("");
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);
  const [responseStyle, setResponseStyle] = useState<ResponseStyle>("detailed");
  const [includeCitations, setIncludeCitations] = useState(true);
  const [showSources, setShowSources] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<AnswerResponse | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await api.answer({
        query: query.trim(),
        top_k: 10,
        candidate_k: 30,
        use_reranker: true,
        filters: selectedDocuments.length ? { document_ids: selectedDocuments } : {},
        max_context_chunks: 6,
        response_style: responseStyle,
        include_citations: includeCitations,
      });
      setResponse(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось получить ответ");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-stack assistant-page">
      <section className="page-heading">
        <div>
          <span className="eyebrow">RAG assistant</span>
          <h1>Ассистент по материалам</h1>
          <p>Ответ формируется только на основе загруженных учебных источников.</p>
        </div>
      </section>

      <div className="assistant-layout">
        <section className="assistant-main">
          <form className="question-card" onSubmit={(event) => void handleSubmit(event)}>
            <div className="question-card__top">
              <span className="assistant-avatar">AI</span>
              <div><strong>Задайте учебный вопрос</strong><small>Система найдёт релевантные фрагменты и приложит цитаты.</small></div>
            </div>
            <textarea
              required
              minLength={2}
              rows={5}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Например: Объясни классификацию артериальной гипертензии и перечисли основные факторы риска"
            />
            <div className="question-card__footer">
              <div className="style-switcher">
                {(Object.keys(STYLE_LABELS) as ResponseStyle[]).map((style) => (
                  <button key={style} type="button" className={responseStyle === style ? "active" : ""} onClick={() => setResponseStyle(style)}>
                    {STYLE_LABELS[style]}
                  </button>
                ))}
              </div>
              <Button type="submit" loading={loading} disabled={!query.trim()} icon={<span>✦</span>}>Получить ответ</Button>
            </div>
          </form>

          {error && <ErrorBanner message={error} />}

          {loading ? (
            <div className="panel center-loader center-loader--large"><Spinner /><p>Ищем контекст и формируем ответ...</p></div>
          ) : !response ? (
            <div className="panel assistant-placeholder">
              <EmptyState icon="✦" title="Ответ появится здесь" text="Для более точного результата можно выбрать конкретные документы справа." />
              <div className="prompt-examples">
                <span>Примеры вопросов</span>
                {["Сделай краткий конспект материала", "Объясни ключевые термины простыми словами", "Сравни два подхода, описанных в лекции"].map((example) => (
                  <button key={example} type="button" onClick={() => setQuery(example)}>{example}</button>
                ))}
              </div>
            </div>
          ) : (
            <article className="answer-card">
              <div className="answer-card__header">
                <div className="answer-card__identity">
                  <span className="assistant-avatar">AI</span>
                  <div><strong>Ответ ассистента</strong><small>{response.used_chunks} фрагментов · {Math.round(response.took_ms)} мс</small></div>
                </div>
                <Tag tone={response.confidence >= 0.7 ? "success" : response.confidence >= 0.4 ? "warning" : "danger"}>
                  {response.confidence >= 0.7 ? "Высокая уверенность" : response.confidence >= 0.4 ? "Средняя уверенность" : "Низкая уверенность"}
                </Tag>
              </div>

              <div className="answer-text">
                {response.answer.split(/\n{2,}/).map((paragraph, index) => <p key={`${paragraph.slice(0, 20)}-${index}`}>{paragraph}</p>)}
              </div>

              <ScoreBar value={response.confidence} />

              {response.limitations.length > 0 && (
                <div className="notice notice--warning"><strong>Ограничения ответа</strong><ul>{response.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>
              )}

              {response.safety_notes.length > 0 && (
                <div className="notice notice--info"><strong>Важно</strong><ul>{response.safety_notes.map((item) => <li key={item}>{item}</li>)}</ul></div>
              )}

              {response.citations.length > 0 && (
                <section className="citations-section">
                  <div className="citations-section__heading">
                    <div><h3>Источники</h3><span>{response.citations.length} цитат</span></div>
                    <button type="button" onClick={() => setShowSources((value) => !value)}>{showSources ? "Свернуть" : "Показать все"}</button>
                  </div>
                  <div className={`citation-list${showSources ? " citation-list--expanded" : ""}`}>
                    {response.citations.map((citation) => (
                      <article className="citation-card" key={citation.chunk_id}>
                        <span className="citation-number">{citation.number}</span>
                        <div>
                          <div className="citation-card__title"><strong>{citation.document_title}</strong><span>{pageLabel(citation.page_start, citation.page_end)}</span></div>
                          {citation.section_title && <small>§ {citation.section_title}</small>}
                          <blockquote>{citation.quote}</blockquote>
                          <div className="citation-card__scores"><span>Retriever {formatScore(citation.retrieval_score)}</span><span>Reranker {formatScore(citation.rerank_score)}</span></div>
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              )}
            </article>
          )}
        </section>

        <aside className="panel assistant-sidebar">
          <div className="assistant-sidebar__heading">
            <div><strong>Контекст ответа</strong><small>Ограничьте поиск выбранными материалами.</small></div>
            {selectedDocuments.length > 0 && <button type="button" onClick={() => setSelectedDocuments([])}>Сбросить</button>}
          </div>
          <DocumentPicker documents={documents} selected={selectedDocuments} onChange={setSelectedDocuments} />
          <hr />
          <label className="check-field check-field--compact">
            <input type="checkbox" checked={includeCitations} onChange={(event) => setIncludeCitations(event.target.checked)} />
            <span><strong>Добавлять цитаты</strong><small>Показывать использованные chunks и страницы.</small></span>
          </label>
          <div className="sidebar-note"><span>i</span><p>Ассистент предназначен для обучения и не заменяет клинические рекомендации или решение врача.</p></div>
        </aside>
      </div>
    </div>
  );
}
