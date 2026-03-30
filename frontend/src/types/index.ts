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

export type FileStatus = 'uploaded' | 'parsing' | 'parsed' | 'parse_error';

export interface SourceFileRead {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  status: FileStatus;
  error_message?: string;
  uploaded_at: string;
  user_id: string;
}

export interface TemplateSection {
  key: string;
  title: string;
  description?: string;
  required?: boolean;
}

export interface TemplateList {
  id: string;
  slug: string;
  name: string;
  version: number;
  document_type: string;
  is_active: boolean;
  created_at: string;
}

export interface TemplateRead extends TemplateList {
  description?: string;
  sections: TemplateSection[];
  schema: Record<string, unknown>;
  rules?: string[];
  updated_at: string;
}

export type ReportStatus = 'pending' | 'processing' | 'done' | 'error';

export interface ValidationError {
  severity: 'error' | 'warning' | 'info';
  type: string;
  section?: string;
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
  template_id: string;
  template_name?: string;
  template_version?: number;
  source_file_ids: string[];
  user_id: string;
  username?: string;
  created_at: string;
  completed_at?: string;
  error_message?: string;
  generation_params?: Record<string, unknown>;
}

export interface ReportDetail extends ReportRead {
  validation_errors: ValidationError[];
  rag_debug?: RagDebug;
  llm_model?: string;
  processing_time_seconds?: number;
  source_files?: SourceFileRead[];
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
