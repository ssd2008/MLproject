import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { DocumentItem, DocumentStatus, JobItem, SourceType } from "../api/types";
import { Button, EmptyState, ErrorBanner, Modal, Spinner, Tag } from "../components/ui";
import {
  cleanOptional,
  formatBytes,
  formatDate,
  formatTimecode,
  sleep,
  SOURCE_LABELS,
  STATUS_LABELS,
} from "../utils";

type UploadMode = "pdf" | "video" | "url" | "text";

interface DocumentsPageProps {
  documents: DocumentItem[];
  loading: boolean;
  error: string | null;
  refreshDocuments: () => Promise<void>;
  notify: (message: string, tone?: "success" | "error") => void;
}

const MAX_PDF_SIZE_MB = 10;
const MAX_VIDEO_SIZE_MB = 2 * 1024;
const STATUS_TONES: Record<DocumentStatus, string> = {
  uploaded: "warning",
  processing: "info",
  ready: "success",
  failed: "danger",
};

function sourceMark(sourceType: SourceType): string {
  if (sourceType === "pdf") return "PDF";
  if (sourceType === "video") return "▶";
  if (sourceType === "url") return "↗";
  return "TXT";
}

function durationSeconds(document: DocumentItem): number | null {
  const value = document.metadata.duration_seconds;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function uploadLimitLabel(mode: UploadMode): string {
  return mode === "video" ? "2 ГБ" : `${MAX_PDF_SIZE_MB} МБ`;
}

export function DocumentsPage({
  documents,
  loading,
  error,
  refreshDocuments,
  notify,
}: DocumentsPageProps) {
  const [showUpload, setShowUpload] = useState(false);
  const [uploadMode, setUploadMode] = useState<UploadMode>("pdf");
  const [submitting, setSubmitting] = useState(false);
  const [activeJobs, setActiveJobs] = useState<Record<string, JobItem>>({});
  const [statusFilter, setStatusFilter] = useState<DocumentStatus | "">("");
  const [sourceFilter, setSourceFilter] = useState<SourceType | "">("");
  const [query, setQuery] = useState("");

  const [title, setTitle] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [language, setLanguage] = useState("ru");
  const [lectureDate, setLectureDate] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [rawText, setRawText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [autoIndex, setAutoIndex] = useState(true);

  const filteredDocuments = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("ru-RU");
    return documents.filter((document) => {
      if (statusFilter && document.status !== statusFilter) return false;
      if (sourceFilter && document.source_type !== sourceFilter) return false;
      if (!normalizedQuery) return true;
      return [document.title, document.specialty, document.original_filename]
        .filter(Boolean)
        .some((value) => value!.toLocaleLowerCase("ru-RU").includes(normalizedQuery));
    });
  }, [documents, query, sourceFilter, statusFilter]);

  const stats = useMemo(
    () => ({
      total: documents.length,
      ready: documents.filter((document) => document.status === "ready").length,
      chunks: documents.reduce((sum, document) => sum + document.chunk_count, 0),
      failed: documents.filter((document) => document.status === "failed").length,
    }),
    [documents],
  );

  function resetForm() {
    setTitle("");
    setSpecialty("");
    setLanguage("ru");
    setLectureDate("");
    setSourceUrl("");
    setRawText("");
    setFile(null);
    setAutoIndex(true);
  }

  function selectMode(mode: UploadMode) {
    setUploadMode(mode);
    setFile(null);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selectedFile = event.target.files?.[0] || null;
    const maxMb = uploadMode === "video" ? MAX_VIDEO_SIZE_MB : MAX_PDF_SIZE_MB;
    if (selectedFile && selectedFile.size > maxMb * 1024 * 1024) {
      event.target.value = "";
      setFile(null);
      notify(`Размер файла не должен превышать ${uploadLimitLabel(uploadMode)}`, "error");
      return;
    }
    setFile(selectedFile);
  }

  async function pollJob(documentId: string, jobId: string, documentTitle: string) {
    for (let attempt = 0; attempt < 3600; attempt += 1) {
      const job = await api.getJob(jobId);
      setActiveJobs((current) => ({ ...current, [documentId]: job }));
      if (job.status === "completed") {
        notify(`«${documentTitle}» проиндексирован`);
        setActiveJobs((current) => {
          const next = { ...current };
          delete next[documentId];
          return next;
        });
        await refreshDocuments();
        return;
      }
      if (job.status === "failed") {
        throw new Error(job.error_message || "Индексация завершилась с ошибкой");
      }
      await sleep(2000);
    }
    throw new Error("Индексация выполняется слишком долго. Проверьте статус позже.");
  }

  async function runIndex(documentId: string, documentTitle: string) {
    try {
      const response = await api.indexDocument(documentId);
      setActiveJobs((current) => ({
        ...current,
        [documentId]: {
          id: response.job_id,
          document_id: documentId,
          status: response.status,
          progress: 0,
          chunk_size: 0,
          chunk_overlap: 0,
          result: {},
          error_message: null,
          created_at: new Date().toISOString(),
          started_at: null,
          finished_at: null,
          updated_at: new Date().toISOString(),
        },
      }));
      await refreshDocuments();
      await pollJob(documentId, response.job_id, documentTitle);
    } catch (caught) {
      notify(caught instanceof Error ? caught.message : "Не удалось запустить индексацию", "error");
      setActiveJobs((current) => {
        const next = { ...current };
        delete next[documentId];
        return next;
      });
      await refreshDocuments();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try {
      let document: DocumentItem;
      if (uploadMode === "pdf" || uploadMode === "video") {
        if (!file) throw new Error(uploadMode === "video" ? "Выберите видеофайл" : "Выберите PDF-файл");
        const maxMb = uploadMode === "video" ? MAX_VIDEO_SIZE_MB : MAX_PDF_SIZE_MB;
        if (file.size > maxMb * 1024 * 1024) {
          throw new Error(`Размер файла не должен превышать ${uploadLimitLabel(uploadMode)}`);
        }
        const form = new FormData();
        form.append("file", file);
        form.append("title", title.trim());
        form.append("language", language.trim());
        if (specialty.trim()) form.append("specialty", specialty.trim());
        if (lectureDate) form.append("lecture_date", lectureDate);
        document = uploadMode === "video" ? await api.uploadVideo(form) : await api.uploadPdf(form);
      } else {
        document = await api.createDocument({
          title: title.trim(),
          source_type: uploadMode,
          source_url: uploadMode === "url" ? sourceUrl.trim() : undefined,
          raw_text: uploadMode === "text" ? rawText.trim() : undefined,
          specialty: cleanOptional(specialty),
          lecture_date: lectureDate || undefined,
          language: language.trim(),
        });
      }

      notify(`Документ «${document.title}» добавлен`);
      setShowUpload(false);
      resetForm();
      await refreshDocuments();
      if (autoIndex) void runIndex(document.id, document.title);
    } catch (caught) {
      const message = caught instanceof ApiError || caught instanceof Error ? caught.message : "Ошибка загрузки";
      notify(message, "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(document: DocumentItem) {
    if (!window.confirm(`Удалить «${document.title}» и все его фрагменты из индекса?`)) return;
    try {
      await api.deleteDocument(document.id);
      notify(`Документ «${document.title}» удалён`);
      await refreshDocuments();
    } catch (caught) {
      notify(caught instanceof Error ? caught.message : "Не удалось удалить документ", "error");
    }
  }

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <span className="eyebrow">База знаний</span>
          <h1>Учебные материалы</h1>
          <p>Загружайте PDF, видео, ссылки и тексты, затем индексируйте их для поиска.</p>
        </div>
        <Button icon={<span>＋</span>} onClick={() => setShowUpload(true)}>Добавить материал</Button>
      </section>

      <section className="stats-grid">
        <article className="stat-card"><span>Всего материалов</span><strong>{stats.total}</strong><small>PDF, видео, URL и текст</small></article>
        <article className="stat-card"><span>Готовы к поиску</span><strong>{stats.ready}</strong><small>Проиндексированные источники</small></article>
        <article className="stat-card"><span>Фрагментов</span><strong>{stats.chunks}</strong><small>Chunks в Qdrant</small></article>
        <article className={`stat-card${stats.failed ? " stat-card--alert" : ""}`}><span>Ошибки</span><strong>{stats.failed}</strong><small>{stats.failed ? "Требуют внимания" : "Система в норме"}</small></article>
      </section>

      <section className="panel">
        <div className="toolbar">
          <div className="search-control"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти материал" /></div>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as DocumentStatus | "")}>
            <option value="">Все статусы</option><option value="uploaded">Загружен</option><option value="processing">Индексируется</option><option value="ready">Готов</option><option value="failed">Ошибка</option>
          </select>
          <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as SourceType | "")}>
            <option value="">Все источники</option><option value="pdf">PDF</option><option value="video">Видео</option><option value="url">URL</option><option value="text">Текст</option>
          </select>
          <Button variant="ghost" onClick={() => void refreshDocuments()} loading={loading}>Обновить</Button>
        </div>

        {error && <ErrorBanner message={error} onRetry={() => void refreshDocuments()} />}
        {loading && documents.length === 0 ? (
          <div className="center-loader"><Spinner /></div>
        ) : filteredDocuments.length === 0 ? (
          <EmptyState icon="▤" title={documents.length ? "Ничего не найдено" : "Материалов пока нет"} text="Добавьте PDF, видео, URL или текст." action={!documents.length ? <Button onClick={() => setShowUpload(true)}>Добавить первый материал</Button> : undefined} />
        ) : (
          <div className="documents-grid">
            {filteredDocuments.map((document) => {
              const job = activeJobs[document.id];
              const isIndexing = Boolean(job) || document.status === "processing";
              const duration = durationSeconds(document);
              return (
                <article className="document-card" key={document.id}>
                  <div className="document-card__top">
                    <div className={`source-icon source-icon--${document.source_type}`}>{sourceMark(document.source_type)}</div>
                    <div className="document-card__title">
                      <h3>{document.title}</h3>
                      <div className="tag-row"><Tag>{SOURCE_LABELS[document.source_type]}</Tag><Tag tone={STATUS_TONES[document.status]}>{STATUS_LABELS[document.status]}</Tag></div>
                    </div>
                    <button className="icon-button" type="button" onClick={() => void handleDelete(document)} aria-label="Удалить">×</button>
                  </div>
                  <dl className="document-meta">
                    <div><dt>Специальность</dt><dd>{document.specialty || "Не указана"}</dd></div>
                    <div><dt>Язык</dt><dd>{document.language.toUpperCase()}</dd></div>
                    <div><dt>Фрагменты</dt><dd>{document.chunk_count}</dd></div>
                    <div><dt>Размер</dt><dd>{formatBytes(document.size_bytes)}</dd></div>
                    <div><dt>{document.source_type === "video" ? "Длительность" : "Дата лекции"}</dt><dd>{document.source_type === "video" ? formatTimecode(duration) : formatDate(document.lecture_date)}</dd></div>
                    <div><dt>Добавлен</dt><dd>{formatDate(document.created_at)}</dd></div>
                  </dl>
                  {document.source_url && <a className="source-link" href={document.source_url} target="_blank" rel="noreferrer">Открыть источник ↗</a>}
                  {document.error_message && <div className="inline-alert">{document.error_message}</div>}
                  {isIndexing && (
                    <div className="job-progress">
                      <div><span>{document.source_type === "video" ? "Расшифровка и индексация" : "Индексация"}</span><strong>{job?.progress ?? 0}%</strong></div>
                      <div className="job-progress__track"><span style={{ width: `${job?.progress ?? 8}%` }} /></div>
                    </div>
                  )}
                  <div className="document-card__actions">
                    <Button variant={document.status === "ready" ? "secondary" : "primary"} loading={isIndexing} onClick={() => void runIndex(document.id, document.title)}>
                      {document.status === "ready" ? "Переиндексировать" : "Индексировать"}
                    </Button>
                    <span className="document-id" title={document.id}>{document.id.slice(0, 8)}</span>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {showUpload && (
        <Modal title="Добавить учебный материал" subtitle="Видео будет расшифровано локальной Whisper-моделью во время индексации." onClose={() => !submitting && setShowUpload(false)}>
          <form className="upload-form" onSubmit={(event) => void handleSubmit(event)}>
            <div className="segmented-control" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
              {(["pdf", "video", "url", "text"] as UploadMode[]).map((mode) => (
                <button key={mode} className={uploadMode === mode ? "active" : ""} type="button" onClick={() => selectMode(mode)}>
                  {mode === "pdf" ? "PDF" : mode === "video" ? "Видео" : mode === "url" ? "Ссылка" : "Текст"}
                </button>
              ))}
            </div>
            <label className="field"><span>Название <b>*</b></span><input required minLength={1} maxLength={300} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, Лекция по кардиологии" /></label>

            {(uploadMode === "pdf" || uploadMode === "video") && (
              <label className={`file-drop${file ? " file-drop--selected" : ""}`}>
                <input type="file" accept={uploadMode === "video" ? "video/mp4,video/quicktime,video/webm,video/x-matroska,video/matroska,.mkv,.MKV,.m4v" : "application/pdf,.pdf"} onChange={handleFileChange} />
                <span className="file-drop__icon">⇧</span>
                <strong>{file ? file.name : uploadMode === "video" ? "Выберите видеофайл" : "Выберите PDF-файл"}</strong>
                <small>{file ? formatBytes(file.size) : uploadMode === "video" ? "MP4, MOV, MKV, WEBM или M4V · до 2 ГБ" : `До ${MAX_PDF_SIZE_MB} МБ, требуется текстовый слой`}</small>
              </label>
            )}
            {uploadMode === "url" && <label className="field"><span>URL источника <b>*</b></span><input required type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://example.com/article" /></label>}
            {uploadMode === "text" && <label className="field"><span>Содержимое <b>*</b></span><textarea required minLength={1} rows={9} value={rawText} onChange={(event) => setRawText(event.target.value)} /></label>}

            <div className="form-grid">
              <label className="field"><span>Специальность</span><input maxLength={100} value={specialty} onChange={(event) => setSpecialty(event.target.value)} placeholder="cardiology" /></label>
              <label className="field"><span>Язык</span><input required minLength={2} maxLength={16} value={language} onChange={(event) => setLanguage(event.target.value)} /></label>
              <label className="field"><span>Дата лекции</span><input type="date" value={lectureDate} onChange={(event) => setLectureDate(event.target.value)} /></label>
            </div>
            <label className="check-field">
              <input type="checkbox" checked={autoIndex} onChange={(event) => setAutoIndex(event.target.checked)} />
              <span><strong>Индексировать сразу после загрузки</strong><small>{uploadMode === "video" ? "Видео будет расшифровано, разбито на ~10-секундные фрагменты и добавлено в поиск." : "Документ будет разбит на фрагменты и добавлен в поиск."}</small></span>
            </label>
            <div className="modal__actions">
              <Button type="button" variant="ghost" onClick={() => setShowUpload(false)} disabled={submitting}>Отмена</Button>
              <Button type="submit" loading={submitting}>Добавить материал</Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
