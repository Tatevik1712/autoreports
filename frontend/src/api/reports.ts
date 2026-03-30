import { MOCK_ENABLED } from '@/mocks/enabled';
import { mockReports, mockReportsList } from '@/mocks/data';
import apiClient from './client';
import type { PaginatedResponse, ReportRead, ReportDetail, CreateReportRequest } from '@/types';

let localMockReports = [...mockReports];
let reportIdCounter = 100;

export const createReport = async (req: CreateReportRequest): Promise<ReportRead> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 500));
    const newReport: ReportDetail = {
      id: `r-mock-${reportIdCounter++}`,
      title: req.title,
      status: 'pending',
      template_id: req.template_id,
      template_name: 'Шаблон',
      source_file_ids: req.source_file_ids,
      user_id: 'u2',
      username: 'ivanov',
      created_at: new Date().toISOString(),
      validation_errors: [],
    };
    localMockReports = [newReport, ...localMockReports];
    return newReport;
  }
  const { data } = await apiClient.post<ReportRead>('/reports', req);
  return data;
};

export const getReports = async (
  page = 1,
  pageSize = 20,
  status?: string
): Promise<PaginatedResponse<ReportRead>> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 300));
    let items: ReportRead[] = localMockReports.map(
      ({ rag_debug, validation_errors, source_files, llm_model, processing_time_seconds, ...rest }) => rest
    );
    if (status && status !== 'all') {
      items = items.filter((r) => r.status === status);
    }
    const start = (page - 1) * pageSize;
    const paged = items.slice(start, start + pageSize);
    return { total: items.length, page, page_size: pageSize, items: paged };
  }
  const { data } = await apiClient.get<PaginatedResponse<ReportRead>>('/reports', {
    params: { page, page_size: pageSize, ...(status && status !== 'all' ? { status } : {}) },
  });
  return data;
};

export const getReport = async (id: string): Promise<ReportDetail> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 300));
    const report = localMockReports.find((r) => r.id === id);
    if (!report) throw new Error('Отчёт не найден');
    return report;
  }
  const { data } = await apiClient.get<ReportDetail>(`/reports/${id}`);
  return data;
};

export const downloadReport = async (id: string): Promise<{ blob: Blob; filename: string }> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 500));
    const report = localMockReports.find((r) => r.id === id);
    const content = `Демо-отчёт: ${report?.title ?? 'Без названия'}`;
    const blob = new Blob([content], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
    return { blob, filename: `${report?.title ?? 'report'}.docx` };
  }
  const response = await apiClient.get(`/reports/${id}/download`, {
    responseType: 'blob',
  });
  const disposition = response.headers['content-disposition'];
  let filename = 'report.docx';
  if (disposition) {
    const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
    if (match?.[1]) filename = match[1].replace(/['"]/g, '');
  }
  return { blob: response.data, filename };
};

export const regenerateReport = async (
  id: string,
  generationParams?: Record<string, unknown>
): Promise<ReportRead> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 500));
    const orig = localMockReports.find((r) => r.id === id);
    if (!orig) throw new Error('Отчёт не найден');
    const newReport: ReportDetail = {
      ...orig,
      id: `r-mock-${reportIdCounter++}`,
      status: 'pending',
      created_at: new Date().toISOString(),
      completed_at: undefined,
      error_message: undefined,
      validation_errors: [],
    };
    localMockReports = [newReport, ...localMockReports];
    return newReport;
  }
  const { data } = await apiClient.post<ReportRead>(`/reports/${id}/regenerate`, {
    generation_params: generationParams,
  });
  return data;
};

export const deleteReport = async (id: string): Promise<void> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 300));
    localMockReports = localMockReports.filter((r) => r.id !== id);
    return;
  }
  await apiClient.delete(`/reports/${id}`);
};
