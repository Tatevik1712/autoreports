import { useParams, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { downloadReport, regenerateReport, deleteReport } from '@/api/reports';
import { useReportPolling } from '@/hooks/useReportPolling';
import { useAuthStore } from '@/store/authStore';
import { StatusBadge } from '@/components/StatusBadge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import {
  Download,
  RefreshCw,
  Trash2,
  Loader2,
  CheckCircle,
  AlertTriangle,
  Info,
  XCircle,
  Clock,
  ChevronDown,
  FileText,
} from 'lucide-react';
import type { ValidationError } from '@/types';

function SeverityIcon({ severity }: { severity: ValidationError['severity'] }) {
  switch (severity) {
    case 'error': return <XCircle className="h-4 w-4 text-destructive" />;
    case 'warning': return <AlertTriangle className="h-4 w-4 text-warning" />;
    case 'info': return <Info className="h-4 w-4 text-info" />;
  }
}

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  const { data: report, isLoading } = useReportPolling(id!);

  const downloadMut = useMutation({
    mutationFn: () => downloadReport(id!),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    },
    onError: () => toast.error('Не удалось скачать файл'),
  });

  const regenMut = useMutation({
    mutationFn: () => regenerateReport(id!),
    onSuccess: (data) => {
      toast.success('Отчёт отправлен на перегенерацию');
      navigate(`/reports/${data.id}`);
    },
    onError: () => toast.error('Ошибка перегенерации'),
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteReport(id!),
    onSuccess: () => {
      toast.success('Отчёт удалён');
      queryClient.invalidateQueries({ queryKey: ['reports'] });
      navigate('/reports');
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-4 max-w-4xl mx-auto">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!report) {
    return <p className="text-muted-foreground">Отчёт не найден</p>;
  }

  const errorCount = report.validation_errors?.filter((e) => e.severity === 'error').length ?? 0;
  const warnCount = report.validation_errors?.filter((e) => e.severity === 'warning').length ?? 0;
  const infoCount = report.validation_errors?.filter((e) => e.severity === 'info').length ?? 0;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{report.title}</h1>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <StatusBadge status={report.status} />
            <span className="text-sm text-muted-foreground">
              {new Date(report.created_at).toLocaleString('ru-RU')}
            </span>
            {report.llm_model && (
              <Badge variant="secondary" className="text-xs">{report.llm_model}</Badge>
            )}
            {report.template_name && (
              <Badge variant="outline" className="text-xs">
                {report.template_name} v{report.template_version}
              </Badge>
            )}
            {report.processing_time_seconds != null && (
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {report.processing_time_seconds.toFixed(1)}с
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {report.status === 'done' && (
            <Button
              size="sm"
              onClick={() => downloadMut.mutate()}
              disabled={downloadMut.isPending}
              className="bg-accent hover:bg-accent/90 text-accent-foreground"
            >
              {downloadMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
              Скачать DOCX
            </Button>
          )}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button size="sm" variant="outline">
                <RefreshCw className="mr-2 h-4 w-4" />Перегенерировать
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Перегенерировать отчёт?</AlertDialogTitle>
                <AlertDialogDescription>Будет создан новый отчёт на основе тех же данных.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Отмена</AlertDialogCancel>
                <AlertDialogAction onClick={() => regenMut.mutate()}>Подтвердить</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button size="sm" variant="outline" className="text-destructive hover:text-destructive">
                <Trash2 className="mr-2 h-4 w-4" />Удалить
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Удалить отчёт?</AlertDialogTitle>
                <AlertDialogDescription>Это действие нельзя отменить.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Отмена</AlertDialogCancel>
                <AlertDialogAction className="bg-destructive text-destructive-foreground" onClick={() => deleteMut.mutate()}>Удалить</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {/* Processing status */}
      {report.status === 'pending' && (
        <Card className="border-info/20 bg-info/5">
          <CardContent className="flex items-center gap-3 py-6">
            <Clock className="h-6 w-6 text-info" />
            <div>
              <p className="font-medium">Ожидает в очереди...</p>
              <p className="text-sm text-muted-foreground">Отчёт скоро начнёт генерироваться</p>
            </div>
          </CardContent>
        </Card>
      )}

      {report.status === 'processing' && (
        <Card className="border-accent/20 bg-accent/5 animate-pulse-processing">
          <CardContent className="flex items-center gap-3 py-6">
            <Loader2 className="h-6 w-6 text-accent animate-spin" />
            <div>
              <p className="font-medium">Генерация отчёта...</p>
              <p className="text-sm text-muted-foreground">Пожалуйста, подождите</p>
            </div>
          </CardContent>
        </Card>
      )}

      {report.status === 'error' && (
        <Card className="border-destructive/20 bg-destructive/5">
          <CardContent className="flex items-center gap-3 py-6">
            <XCircle className="h-6 w-6 text-destructive" />
            <div className="flex-1">
              <p className="font-medium text-destructive">Ошибка генерации</p>
              <p className="text-sm text-muted-foreground">{report.error_message || 'Неизвестная ошибка'}</p>
            </div>
            <Button size="sm" variant="outline" onClick={() => regenMut.mutate()}>
              Попробовать снова
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Source files */}
      {report.source_files && report.source_files.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Исходные файлы</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-1">
              {report.source_files.map((f) => (
                <div key={f.id} className="flex items-center gap-2 text-sm p-2 rounded hover:bg-muted/30">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <span>{f.filename}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Validation errors */}
      {report.status === 'done' && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Нормоконтроль</CardTitle>
              <div className="flex gap-2">
                {errorCount > 0 && <Badge className="severity-error border text-xs">{errorCount} ошибок</Badge>}
                {warnCount > 0 && <Badge className="severity-warning border text-xs">{warnCount} предупреждений</Badge>}
                {infoCount > 0 && <Badge className="severity-info border text-xs">{infoCount} заметок</Badge>}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {report.validation_errors.length === 0 ? (
              <div className="flex items-center gap-2 rounded-md bg-success/10 p-4 text-success">
                <CheckCircle className="h-5 w-5" />
                <span className="font-medium">Ошибок нормоконтроля не найдено</span>
              </div>
            ) : (
              <div className="space-y-2">
                {report.validation_errors.map((e, i) => (
                  <div key={i} className={`rounded-md border p-3 severity-${e.severity}`}>
                    <div className="flex items-start gap-2">
                      <SeverityIcon severity={e.severity} />
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">{e.type}</span>
                          {e.section && <Badge variant="outline" className="text-xs">{e.section}</Badge>}
                        </div>
                        <p className="text-sm mt-1">{e.message}</p>
                        {e.recommendation && (
                          <p className="text-xs text-muted-foreground mt-1">💡 {e.recommendation}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* RAG Debug (admin only) */}
      {isAdmin && report.rag_debug && (
        <Collapsible>
          <Card>
            <CollapsibleTrigger className="w-full">
              <CardHeader className="flex flex-row items-center justify-between cursor-pointer">
                <CardTitle className="text-base">Диагностика RAG</CardTitle>
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center p-3 rounded-md bg-muted/50">
                    <p className="text-2xl font-bold">{report.rag_debug.total_chunks}</p>
                    <p className="text-xs text-muted-foreground">Чанков</p>
                  </div>
                  <div className="text-center p-3 rounded-md bg-muted/50">
                    <p className="text-2xl font-bold">{report.rag_debug.total_tables}</p>
                    <p className="text-xs text-muted-foreground">Таблиц</p>
                  </div>
                  <div className="text-center p-3 rounded-md bg-muted/50">
                    <p className="text-2xl font-bold">{report.rag_debug.total_numeric_blocks}</p>
                    <p className="text-xs text-muted-foreground">Числовых блоков</p>
                  </div>
                </div>

                {report.rag_debug.chunks.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-sm font-medium">Найденные чанки</h4>
                    {report.rag_debug.chunks.map((c, i) => (
                      <div key={i} className="rounded border p-2 text-xs space-y-1">
                        <div className="flex justify-between">
                          <span className="font-medium">{c.query}</span>
                          <Badge variant="secondary" className="text-[10px]">
                            score: {c.score.toFixed(3)}
                          </Badge>
                        </div>
                        <p className="text-muted-foreground line-clamp-2">{c.preview}</p>
                      </div>
                    ))}
                  </div>
                )}

                {report.rag_debug.indexing_errors && report.rag_debug.indexing_errors.length > 0 && (
                  <div className="space-y-1">
                    <h4 className="text-sm font-medium text-destructive">Ошибки индексации</h4>
                    {report.rag_debug.indexing_errors.map((e, i) => (
                      <p key={i} className="text-xs text-destructive">{e}</p>
                    ))}
                  </div>
                )}
              </CardContent>
            </CollapsibleContent>
          </Card>
        </Collapsible>
      )}
    </div>
  );
}
