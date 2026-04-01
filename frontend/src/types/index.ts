export type UserRole = 'user' | 'admin';

export interface UserRead {
  id: string;
  email: string;
  username: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

// FileStatus включает 'parsing' для совместимости с мок-данными
export type FileStatus = 'uploaded' | 'parsing' | 'parsed' | 'parse_error';

export interface SourceFileRead {
  id: string;
  // Backend отдаёт оба поля: original_filename и filename (алиас)
  original_filename: string;
  filename: string;          // алиас = original_filename
  content_type: string;
  size_bytes: number;
  size: number;              // алиас = size_bytes
  status: FileStatus;
  parse_error: string | null;
  error_message: string | null;  // алиас = parse_error
  meta: Record<string, unknown>;
  uploaded_at: string;
  user_id: string;
}

export interface TemplateSection {
  id: string;
  key: string;               // алиас = id (backend добавляет оба)
  title: string;
  description?: string;
  required?: boolean;
  rules?: string[];
  fields?: unknown[];
}

export interface TemplateList {
  id: string;
  slug: string;
  name: string;
  version: number;
  document_type: string;     // backend извлекает из schema.document_type
  is_active: boolean;
  created_at: string;
  description?: string;
}

export interface TemplateRead extends TemplateList {
  schema: Record<string, unknown>;
  sections: TemplateSection[];  // backend извлекает из schema.sections
  rules: string[];              // backend извлекает из schema.global_rules
  updated_at: string;
}

export type ReportStatus = 'pending' | 'processing' | 'done' | 'error';

export interface ValidationError {
  severity: 'error' | 'warning' | 'info';
  type: string;
  section?: string;          // = section_id из backend
  section_id?: string;
  message: string;
  recommendation?: string;
}

export interface RagChunk {
  query: string;
  score: number;
  preview: string;
  section?: string;
}

export interface RagDebug {
  total_chunks: number;
  total_tables: number;
  total_numeric_blocks: number;
  document_map?: Record<string, unknown>;
  chunks: RagChunk[];
  indexing_errors?: string[];
}

export interface ReportRead {
  id: string;
  title: string;
  status: ReportStatus;
  template_id: string | null;
  template_name?: string;    // backend добавляет из template.name
  template_version?: number;
  source_file_ids: string[];
  user_id: string | null;
  username?: string;         // backend добавляет из owner.username
  created_at: string;
  completed_at?: string;
  error_message?: string | null;
  generation_params?: Record<string, unknown>;
  llm_model?: string | null;
  processing_seconds?: number | null;
  processing_time_seconds?: number | null; // алиас для frontend
}

export interface ReportDetail extends ReportRead {
  validation_errors: ValidationError[];
  rag_debug?: RagDebug;      // backend извлекает из generation_params._rag_stats
  source_files?: SourceFileRead[];
  owner?: UserRead;
  template?: TemplateList;
}

export interface CreateReportRequest {
  title: string;
  template_id: string;
  source_file_ids: string[];
  generation_params?: Record<string, unknown>;
}

export interface CreateTemplateRequest {
  name: string;
  slug: string;
  document_type: string;
  description?: string;
  sections: TemplateSection[];
  schema: Record<string, unknown>;
  rules?: string[];
}
