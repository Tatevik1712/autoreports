import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getReports } from '@/api/reports';
import { useAuthStore } from '@/store/authStore';
import { StatusBadge } from '@/components/StatusBadge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Plus, Search } from 'lucide-react';

export default function ReportsListPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  const { data, isLoading } = useQuery({
    queryKey: ['reports', page, statusFilter],
    queryFn: () => getReports(page, 20, statusFilter),
    refetchInterval: (query) => {
      const items = query.state.data?.items;
      if (items?.some((r) => r.status === 'pending' || r.status === 'processing')) return 5000;
      return false;
    },
  });

  const items = data?.items ?? [];
  const filtered = search
    ? items.filter((r) => r.title.toLowerCase().includes(search.toLowerCase()))
    : items;
  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Отчёты</h1>
        <Button asChild size="sm" className="bg-accent hover:bg-accent/90 text-accent-foreground">
          <Link to="/reports/new"><Plus className="mr-2 h-4 w-4" />Создать отчёт</Link>
        </Button>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Поиск по названию..."
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1); }}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все статусы</SelectItem>
            <SelectItem value="pending">Ожидает</SelectItem>
            <SelectItem value="processing">Обработка</SelectItem>
            <SelectItem value="done">Готов</SelectItem>
            <SelectItem value="error">Ошибка</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-lg border">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : filtered.length === 0 ? (
          <p className="p-8 text-center text-muted-foreground">Отчёты не найдены</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left p-3 font-medium">Название</th>
                {isAdmin && <th className="text-left p-3 font-medium">Владелец</th>}
                <th className="text-left p-3 font-medium">Шаблон</th>
                <th className="text-left p-3 font-medium">Статус</th>
                <th className="text-left p-3 font-medium">Дата</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id} className="border-b last:border-0 hover:bg-muted/20">
                  <td className="p-3">
                    <Link to={`/reports/${r.id}`} className="font-medium text-accent hover:underline">
                      {r.title}
                    </Link>
                  </td>
                  {isAdmin && <td className="p-3 text-muted-foreground">{r.username || '—'}</td>}
                  <td className="p-3 text-muted-foreground">{r.template_name || '—'}</td>
                  <td className="p-3"><StatusBadge status={r.status} /></td>
                  <td className="p-3 text-muted-foreground">
                    {new Date(r.created_at).toLocaleDateString('ru-RU')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(page - 1)}>Назад</Button>
          <span className="flex items-center text-sm text-muted-foreground">{page} из {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page === totalPages} onClick={() => setPage(page + 1)}>Далее</Button>
        </div>
      )}
    </div>
  );
}
