import { MOCK_ENABLED } from '@/mocks/enabled';
import { mockUsers } from '@/mocks/data';
import apiClient from './client';
import type { AuthResponse, UserRead } from '@/types';
import { useAuthStore } from '@/store/authStore';

export const login = async (username: string, password: string): Promise<AuthResponse> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 600));
    const user = mockUsers[username] ?? mockUsers['user'];
    if (!user) throw { response: { status: 401 } };
    return { access_token: `mock-token-${user.id}`, token_type: 'bearer' };
  }
  const formData = new FormData();
  formData.append('username', username);
  formData.append('password', password);
  const { data } = await apiClient.post<AuthResponse>('/auth/login', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

export const getMe = async (): Promise<UserRead> => {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 200));
    const token = useAuthStore.getState().token;
    if (token?.includes('u1')) return mockUsers['admin'];
    return mockUsers['user'];
  }
  const { data } = await apiClient.get<UserRead>('/auth/me');
  return data;
};
