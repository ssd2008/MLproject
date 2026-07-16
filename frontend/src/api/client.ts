import type {
  AnswerRequest,
  AnswerResponse,
  ApiErrorShape,
  CreateDocumentPayload,
  DocumentItem,
  DocumentsListResponse,
  DocumentStatus,
  HealthResponse,
  IndexDocumentResponse,
  JobItem,
  SearchRequest,
  SearchResponse,
  SourceType,
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly context: Record<string, unknown>;

  constructor(status: number, payload: ApiErrorShape) {
    super(payload.detail || `Ошибка API (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = payload.code || "api_error";
    this.context = payload.context || {};
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let payload: ApiErrorShape = { detail: response.statusText };
    try {
      payload = (await response.json()) as ApiErrorShape;
    } catch {
      // The backend can return an empty body for proxy-level errors.
    }
    throw new ApiError(response.status, payload);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export interface DocumentListParams {
  limit?: number;
  offset?: number;
  status?: DocumentStatus | "";
  sourceType?: SourceType | "";
  specialty?: string;
}

export const api = {
  async getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },

  async listDocuments(params: DocumentListParams = {}): Promise<DocumentsListResponse> {
    const search = new URLSearchParams();
    search.set("limit", String(params.limit ?? 100));
    search.set("offset", String(params.offset ?? 0));
    if (params.status) search.set("status", params.status);
    if (params.sourceType) search.set("source_type", params.sourceType);
    if (params.specialty?.trim()) search.set("specialty", params.specialty.trim());
    return request<DocumentsListResponse>(`/documents?${search.toString()}`);
  },

  async createDocument(payload: CreateDocumentPayload): Promise<DocumentItem> {
    return request<DocumentItem>("/documents", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async uploadPdf(formData: FormData): Promise<DocumentItem> {
    return request<DocumentItem>("/documents/upload", {
      method: "POST",
      body: formData,
    });
  },

  async uploadVideo(formData: FormData): Promise<DocumentItem> {
    return request<DocumentItem>("/documents/upload/video", {
      method: "POST",
      body: formData,
    });
  },

  async deleteDocument(documentId: string): Promise<void> {
    return request<void>(`/documents/${documentId}`, { method: "DELETE" });
  },

  async indexDocument(
    documentId: string,
    options: { chunk_size?: number; chunk_overlap?: number } = {},
  ): Promise<IndexDocumentResponse> {
    return request<IndexDocumentResponse>(`/documents/${documentId}/index`, {
      method: "POST",
      body: JSON.stringify(options),
    });
  },

  async getJob(jobId: string): Promise<JobItem> {
    return request<JobItem>(`/jobs/${jobId}`);
  },

  async search(payload: SearchRequest): Promise<SearchResponse> {
    return request<SearchResponse>("/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async answer(payload: AnswerRequest): Promise<AnswerResponse> {
    return request<AnswerResponse>("/answer", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
