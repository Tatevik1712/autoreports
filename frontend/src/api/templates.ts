import { MOCK_ENABLED } from '@/mocks/enabled';
import { mockTemplates, mockTemplatesList } from '@/mocks/data';
import apiClient from './client';
import type { PaginatedResponse, TemplateList, TemplateRead, CreateTemplateRequest } from '@/types';

let localMockTemplates = [...mockTemplates];
let templateIdCounter = 100;

export const getTemplates = async (
  page = 1,
  pageSize = 50
): Promise<PaginatedResponse<TemplateList>> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 300));
    const items: TemplateList[] = localMockTemplates.map(
      ({ id, slug, name, version, document_type, is_active, created_at }) => ({
        id, slug, name, version, document_type, is_active, created_at,
      })
    );
    const start = (page - 1) * pageSize;
    return { total: items.length, page, page_size: pageSize, items: items.slice(start, start + pageSize) };
  }
  const { data } = await apiClient.get<PaginatedResponse<TemplateList>>('/templates', {
    params: { page, page_size: pageSize },
  });
  return data;
};

export const getTemplate = async (id: string): Promise<TemplateRead> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 200));
    const t = localMockTemplates.find((t) => t.id === id);
    if (!t) throw new Error('Шаблон не найден');
    return t;
  }
  const { data } = await apiClient.get<TemplateRead>(`/templates/${id}`);
  return data;
};

export const createTemplate = async (req: CreateTemplateRequest): Promise<TemplateRead> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 400));
    const newT: TemplateRead = {
      id: `t-mock-${templateIdCounter++}`,
      ...req,
      version: 1,
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    localMockTemplates = [newT, ...localMockTemplates];
    return newT;
  }
  const { data } = await apiClient.post<TemplateRead>('/templates', req);
  return data;
};

export const updateTemplate = async (
  id: string,
  req: Partial<CreateTemplateRequest>
): Promise<TemplateRead> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 400));
    const idx = localMockTemplates.findIndex((t) => t.id === id);
    if (idx === -1) throw new Error('Шаблон не найден');
    localMockTemplates[idx] = {
      ...localMockTemplates[idx],
      ...req,
      version: localMockTemplates[idx].version + 1,
      updated_at: new Date().toISOString(),
    };
    return localMockTemplates[idx];
  }
  const { data } = await apiClient.put<TemplateRead>(`/templates/${id}`, req);
  return data;
};

export const deleteTemplate = async (id: string): Promise<void> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 300));
    localMockTemplates = localMockTemplates.filter((t) => t.id !== id);
    return;
  }
  await apiClient.delete(`/templates/${id}`);
};
