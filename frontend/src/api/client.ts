import axios from 'axios';
import { useAuthStore } from '@/store/authStore';
import { toast } from 'sonner';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000/api/v1',
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const status = error.response.status;
      if (status === 401) {
        useAuthStore.getState().clearAuth();
        window.location.href = '/login';
      } else if (status === 422) {
        const detail = error.response.data?.detail;
        const message = Array.isArray(detail)
          ? detail.map((d: { msg: string }) => d.msg).join(', ')
          : typeof detail === 'string'
            ? detail
            : 'Ошибка валидации данных';
        error.message = message;
      } else if (status >= 500) {
        toast.error('Ошибка сервера. Попробуйте позже.');
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
