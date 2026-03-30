import { useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { getFiles, deleteFile } from '@/api/files';
import { FileUploadZone } from '@/components/FileUploadZone';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Trash2, FileIcon } from 'lucide-react';
import { toast } from 'sonner';

export default function FilesPage() {
  const [page, setPage] = useState(1);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['files', page],
    queryFn: () => getFiles(page, 20),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteFile,
    onSuccess: () => {
      toast.success('Файл удалён');
      queryClient.invalidateQueries({ queryKey: ['files'] });
      setDeleteId(null);
    },
    onError: () => toast.error('Не удалось удалить файл'),
  });

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} Б`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
  };

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Мои файлы</h1>

      <FileUploadZone onUploadComplete={() => queryClient.invalidateQueries({ queryKey: ['files'] })} />

      <div className="rounded-lg border">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : data && data.items.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left p-3 font-medium">Файл</th>
                <th className="text-left p-3 font-medium">Размер</th>
                <th className="text-left p-3 font-medium">Статус</th>
                <th className="text-left p-3 font-medium">Дата</th>
                <th className="p-3 w-10" />
              </tr>
            </thead>
            <tbody>
              {data.items.map((f) => (
                <tr key={f.id} className="border-b last:border-0 hover:bg-muted/20">
                  <td className="p-3 flex items-center gap-2">
                    <FileIcon className="h-4 w-4 text-muted-foreground" />
                    <span className="truncate max-w-xs">{f.filename}</span>
                  </td>
                  <td className="p-3 text-muted-foreground">{formatSize(f.size)}</td>
                  <td className="p-3">
                    {f.status === 'parse_error' ? (
                      <Tooltip>
                        <TooltipTrigger>
                          <Badge variant="destructive" className="text-xs">Ошибка</Badge>
                        </TooltipTrigger>
                        <TooltipContent>{f.error_message || 'Ошибка обработки'}</TooltipContent>
                      </Tooltip>
                    ) : f.status === 'parsed' ? (
                      <Badge className="bg-success/10 text-success border-0 text-xs">Обработан</Badge>
                    ) : (
                      <Badge variant="secondary" className="text-xs">{f.status}</Badge>
                    )}
                  </td>
                  <td className="p-3 text-muted-foreground">
                    {new Date(f.uploaded_at).toLocaleDateString('ru-RU')}
                  </td>
                  <td className="p-3">
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={() => setDeleteId(f.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="p-8 text-center text-muted-foreground">Файлы не найдены</p>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(page - 1)}>
            Назад
          </Button>
          <span className="flex items-center text-sm text-muted-foreground">
            {page} из {totalPages}
          </span>
          <Button variant="outline" size="sm" disabled={page === totalPages} onClick={() => setPage(page + 1)}>
            Далее
          </Button>
        </div>
      )}

      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить файл?</AlertDialogTitle>
            <AlertDialogDescription>Это действие нельзя отменить.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteId && deleteMutation.mutate(deleteId)}
            >
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
