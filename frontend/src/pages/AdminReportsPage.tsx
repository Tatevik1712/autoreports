import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getReports } from '@/api/reports';
import { StatusBadge } from '@/components/StatusBadge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Search, ClipboardList, Clock, CheckCircle, XCircle } from 'lucide-react';

export default function AdminReportsPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['admin-reports', page, statusFilter],
    queryFn: () => getReports(page, 20, statusFilter),
    refetchInterval: (query) => {
      const items = query.state.data?.items;
      if (items?.some((r) => r.status === 'pending' || r.status === 'processing')) return 5000;
      return false;
    },
  });

  const items = data?.items ?? [];
  const filtered = search
    ? items.filter((r) =>
        r.title.toLowerCase().includes(search.toLowerCase()) ||
        (r.username || '').toLowerCase().includes(search.toLowerCase())
      )
    : items;
  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;

  // Stats
  const allItems = data?.items ?? [];
  const pendingCount = allItems.filter((r) => r.status === 'pending' || r.status === 'processing').length;
  const doneCount = allItems.filter((r) => r.status === 'done').length;
  const errorCount = allItems.filter((r) => r.status === 'error').length;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Все отчёты</h1>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Всего</CardTitle>
            <ClipboardList className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-7 w-12" /> : <p className="text-2xl font-bold">{data?.total ?? 0}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">В обработке</CardTitle>
            <Clock className="h-4 w-4 text-info" />
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-7 w-12" /> : <p className="text-2xl font-bold">{pendingCount}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Готовых</CardTitle>
            <CheckCircle className="h-4 w-4 text-success" />
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-7 w-12" /> : <p className="text-2xl font-bold">{doneCount}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">С ошибками</CardTitle>
            <XCircle className="h-4 w-4 text-destructive" />
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-7 w-12" /> : <p className="text-2xl font-bold">{errorCount}</p>}
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Поиск по названию или владельцу..." className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
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
                <th className="text-left p-3 font-medium">Владелец</th>
                <th className="text-left p-3 font-medium">Шаблон</th>
                <th className="text-left p-3 font-medium">Статус</th>
                <th className="text-left p-3 font-medium">Дата</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id} className="border-b last:border-0 hover:bg-muted/20">
                  <td className="p-3">
                    <Link to={`/reports/${r.id}`} className="font-medium text-accent hover:underline">{r.title}</Link>
                  </td>
                  <td className="p-3 text-muted-foreground">{r.username || '—'}</td>
                  <td className="p-3 text-muted-foreground">{r.template_name || '—'}</td>
                  <td className="p-3"><StatusBadge status={r.status} /></td>
                  <td className="p-3 text-muted-foreground">{new Date(r.created_at).toLocaleDateString('ru-RU')}</td>
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
