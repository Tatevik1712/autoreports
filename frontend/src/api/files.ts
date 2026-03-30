import { MOCK_ENABLED } from '@/mocks/enabled';
import { mockFiles } from '@/mocks/data';
import apiClient from './client';
import type { PaginatedResponse, SourceFileRead } from '@/types';

let localMockFiles = [...mockFiles];
let fileIdCounter = 100;

export const uploadFile = async (
  file: File,
  onProgress?: (percent: number) => void
): Promise<SourceFileRead> => {
  if (MOCK_ENABLED) {
    for (let i = 0; i <= 100; i += 20) {
      await new Promise((r) => setTimeout(r, 150));
      onProgress?.(i);
    }
    const newFile: SourceFileRead = {
      id: `f-mock-${fileIdCounter++}`,
      filename: file.name,
      content_type: file.type,
      size: file.size,
      status: 'parsed',
      uploaded_at: new Date().toISOString(),
      user_id: 'u2',
    };
    localMockFiles = [newFile, ...localMockFiles];
    return newFile;
  }
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await apiClient.post<SourceFileRead>('/files', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (e.total && onProgress) {
        onProgress(Math.round((e.loaded * 100) / e.total));
      }
    },
  });
  return data;
};

export const getFiles = async (page = 1, pageSize = 20): Promise<PaginatedResponse<SourceFileRead>> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 300));
    const start = (page - 1) * pageSize;
    const items = localMockFiles.slice(start, start + pageSize);
    return { total: localMockFiles.length, page, page_size: pageSize, items };
  }
  const { data } = await apiClient.get<PaginatedResponse<SourceFileRead>>('/files', {
    params: { page, page_size: pageSize },
  });
  return data;
};

export const getFile = async (id: string): Promise<SourceFileRead> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 200));
    const file = localMockFiles.find((f) => f.id === id);
    if (!file) throw new Error('Файл не найден');
    return file;
  }
  const { data } = await apiClient.get<SourceFileRead>(`/files/${id}`);
  return data;
};

export const deleteFile = async (id: string): Promise<void> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 300));
    localMockFiles = localMockFiles.filter((f) => f.id !== id);
    return;
  }
  await apiClient.delete(`/files/${id}`);
};
