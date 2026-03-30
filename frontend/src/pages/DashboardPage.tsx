import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getReports } from '@/api/reports';
import { getFiles } from '@/api/files';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge } from '@/components/StatusBadge';
import {
  ClipboardList,
  Clock,
  CheckCircle,
  FileUp,
  Plus,
  Upload,
} from 'lucide-react';

export default function DashboardPage() {
  const { data: reportsData, isLoading: rLoading } = useQuery({
    queryKey: ['reports', 1],
    queryFn: () => getReports(1, 100),
  });

  const { data: filesData, isLoading: fLoading } = useQuery({
    queryKey: ['files', 1],
    queryFn: () => getFiles(1, 100),
  });

  const reports = reportsData?.items ?? [];
  const totalReports = reports.length;
  const inProgress = reports.filter((r) => r.status === 'pending' || r.status === 'processing').length;
  const doneCount = reports.filter((r) => r.status === 'done').length;
  const totalFiles = filesData?.total ?? 0;
  const latest = reports.slice(0, 5);

  const stats = [
    { title: 'Всего отчётов', value: totalReports, icon: ClipboardList, color: 'text-accent' },
    { title: 'В обработке', value: inProgress, icon: Clock, color: 'text-info' },
    { title: 'Готовых', value: doneCount, icon: CheckCircle, color: 'text-success' },
    { title: 'Файлов', value: totalFiles, icon: FileUp, color: 'text-gold' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Дашборд</h1>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to="/files"><Upload className="mr-2 h-4 w-4" />Загрузить файл</Link>
          </Button>
          <Button asChild size="sm" className="bg-accent hover:bg-accent/90 text-accent-foreground">
            <Link to="/reports/new"><Plus className="mr-2 h-4 w-4" />Создать отчёт</Link>
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s) => (
          <Card key={s.title}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{s.title}</CardTitle>
              <s.icon className={`h-5 w-5 ${s.color}`} />
            </CardHeader>
            <CardContent>
              {rLoading || fLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <p className="text-3xl font-bold">{s.value}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Последние отчёты</CardTitle>
        </CardHeader>
        <CardContent>
          {rLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : latest.length === 0 ? (
            <p className="text-sm text-muted-foreground">Отчётов пока нет</p>
          ) : (
            <div className="space-y-2">
              {latest.map((r) => (
                <Link
                  key={r.id}
                  to={`/reports/${r.id}`}
                  className="flex items-center justify-between rounded-md border p-3 hover:bg-muted/50 transition-colors"
                >
                  <div>
                    <p className="text-sm font-medium">{r.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(r.created_at).toLocaleDateString('ru-RU')}
                    </p>
                  </div>
                  <StatusBadge status={r.status} />
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
