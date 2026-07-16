import { FormEvent, useState } from "react";
import { api } from "../api/client";
import type { DocumentItem, SearchResponse, SourceType } from "../api/types";
import { DocumentPicker } from "../components/DocumentPicker";
import { Button, EmptyState, ErrorBanner, Spinner, Tag } from "../components/ui";
import { formatScore, sourceLocationLabel, SOURCE_LABELS } from "../utils";

export function SearchPage({ documents }: { documents: DocumentItem[] }) {
  const [query, setQuery] = useState("");
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);
  const [specialty, setSpecialty] = useState("");
  const [language, setLanguage] = useState("");
  const [sourceType, setSourceType] = useState<SourceType | "">("");
  const [topK, setTopK] = useState(10);
  const [candidateK, setCandidateK] = useState(30);
  const [useReranker, setUseReranker] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await api.search({
        query: query.trim(),
        top_k: topK,
        candidate_k: Math.max(candidateK, topK),
        use_reranker: useReranker,
        filters: {
          ...(selectedDocuments.length ? { document_ids: selectedDocuments } : {}),
          ...(specialty.trim() ? { specialty: specialty.trim() } : {}),
          ...(language.trim() ? { language: language.trim() } : {}),
          ...(sourceType ? { source_types: [sourceType] } : {}),
        },
      });
      setResponse(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Поиск завершился с ошибкой");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <span className="eyebrow">Retrieval</span>
          <h1>Поиск по материалам</h1>
          <p>Для видео каждый найденный фрагмент содержит примерный тайм-код длительностью около 10 секунд.</p>
        </div>
      </section>

      <div className="split-layout split-layout--search">
        <aside className="panel filter-panel">
          <form onSubmit={(event) => void handleSubmit(event)}>
            <label className="field">
              <span>Поисковый запрос</span>
              <textarea required minLength={2} rows={5} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Например: Какие признаки характерны для артериальной гипертензии?" />
            </label>
            <div className="filter-section">
              <div className="filter-section__heading">
                <strong>Документы</strong>
                {selectedDocuments.length > 0 && <button type="button" onClick={() => setSelectedDocuments([])}>Сбросить</button>}
              </div>
              <DocumentPicker documents={documents} selected={selectedDocuments} onChange={setSelectedDocuments} />
            </div>
            <button className="advanced-toggle" type="button" onClick={() => setShowAdvanced((value) => !value)}>
              <span>Дополнительные параметры</span><span>{showAdvanced ? "−" : "+"}</span>
            </button>
            {showAdvanced && (
              <div className="advanced-fields">
                <div className="form-grid form-grid--two">
                  <label className="field"><span>Специальность</span><input value={specialty} onChange={(event) => setSpecialty(event.target.value)} placeholder="cardiology" /></label>
                  <label className="field"><span>Язык</span><input value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="ru" /></label>
                </div>
                <label className="field">
                  <span>Тип источника</span>
                  <select value={sourceType} onChange={(event) => setSourceType(event.target.value as SourceType | "")}>
                    <option value="">Любой</option><option value="pdf">PDF</option><option value="video">Видео</option><option value="url">URL</option><option value="text">Текст</option>
                  </select>
                </label>
                <div className="form-grid form-grid--two">
                  <label className="field"><span>Результатов top_k</span><input type="number" min={1} max={100} value={topK} onChange={(event) => setTopK(Number(event.target.value))} /></label>
                  <label className="field"><span>Кандидатов candidate_k</span><input type="number" min={1} max={300} value={candidateK} onChange={(event) => setCandidateK(Number(event.target.value))} /></label>
                </div>
                <label className="check-field check-field--compact">
                  <input type="checkbox" checked={useReranker} onChange={(event) => setUseReranker(event.target.checked)} />
                  <span><strong>Использовать reranker</strong><small>Повторно отсортировать кандидатов.</small></span>
                </label>
              </div>
            )}
            <Button className="full-width" type="submit" loading={loading} disabled={!query.trim()} icon={<span>⌕</span>}>Найти фрагменты</Button>
          </form>
        </aside>

        <section className="search-results">
          {error && <ErrorBanner message={error} />}
          {loading ? (
            <div className="panel center-loader center-loader--large"><Spinner /><p>Ищем релевантные фрагменты...</p></div>
          ) : !response ? (
            <div className="panel"><EmptyState icon="⌕" title="Введите вопрос для поиска" text="Здесь появятся chunks, scores, страницы и тайм-коды." /></div>
          ) : response.results.length === 0 ? (
            <div className="panel"><EmptyState icon="∅" title="Результатов нет" text="Попробуйте изменить запрос или снять часть фильтров." /></div>
          ) : (
            <>
              <div className="results-summary">
                <div><span>Найдено</span><strong>{response.results.length} фрагментов</strong></div>
                <div><span>Кандидатов</span><strong>{response.total_candidates}</strong></div>
                <div><span>Время</span><strong>{Math.round(response.took_ms)} мс</strong></div>
              </div>
              <div className="result-list">
                {response.results.map((result) => (
                  <article className="result-card" key={result.chunk_id}>
                    <div className="result-card__rank">#{result.rank}</div>
                    <div className="result-card__content">
                      <div className="result-card__header">
                        <div>
                          <h3>{result.document_title}</h3>
                          <div className="tag-row">
                            <Tag>{SOURCE_LABELS[result.source_type]}</Tag>
                            {result.specialty && <Tag tone="info">{result.specialty}</Tag>}
                            <Tag>{sourceLocationLabel(result.page_start, result.page_end, result.time_start_seconds, result.time_end_seconds)}</Tag>
                          </div>
                        </div>
                        <div className="score-stack"><span>Итоговый score</span><strong>{formatScore(result.final_score)}</strong></div>
                      </div>
                      {result.section_title && <p className="section-label">§ {result.section_title}</p>}
                      <p className="result-text">{result.text}</p>
                      <div className="result-card__footer">
                        <span>Retriever: <strong>{formatScore(result.retrieval_score)}</strong></span>
                        <span>Reranker: <strong>{formatScore(result.rerank_score)}</strong></span>
                        <span>Chunk #{result.chunk_index}</span>
                        {result.source_type === "video" ? (
                          <span><strong>{sourceLocationLabel(null, null, result.time_start_seconds, result.time_end_seconds)}</strong></span>
                        ) : (
                          <span>Символы {result.char_start}–{result.char_end}</span>
                        )}
                        {result.source_url && <a href={result.source_url} target="_blank" rel="noreferrer">Источник ↗</a>}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
