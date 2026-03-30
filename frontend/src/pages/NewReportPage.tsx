import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getFiles } from '@/api/files';
import { getTemplates } from '@/api/templates';
import { createReport } from '@/api/reports';
import { FileUploadZone } from '@/components/FileUploadZone';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Search,
  Check,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export default function NewReportPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [templateSearch, setTemplateSearch] = useState('');
  const [showUpload, setShowUpload] = useState(false);

  const { data: filesData, isLoading: filesLoading } = useQuery({
    queryKey: ['files', 1, 100],
    queryFn: () => getFiles(1, 100),
  });

  const { data: templatesData, isLoading: templatesLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => getTemplates(1, 50),
  });

  const createMutation = useMutation({
    mutationFn: createReport,
    onSuccess: (data) => {
      toast.success('Отчёт создан и отправлен на генерацию');
      navigate(`/reports/${data.id}`);
    },
    onError: () => toast.error('Не удалось создать отчёт'),
  });

  const parsedFiles = filesData?.items.filter((f) => f.status === 'parsed') ?? [];
  const templates = templatesData?.items ?? [];
  const filteredTemplates = templates.filter((t) =>
    t.name.toLowerCase().includes(templateSearch.toLowerCase())
  );
  const selectedTemplateName = templates.find((t) => t.id === selectedTemplate)?.name;

  const toggleFile = (id: string) => {
    setSelectedFiles((prev) =>
      prev.includes(id) ? prev.filter((f) => f !== id) : [...prev, id]
    );
  };

  const canProceedStep1 = selectedFiles.length > 0;
  const canProceedStep2 = !!selectedTemplate;
  const canSubmit = title.trim().length > 0;

  const handleCreate = () => {
    if (!selectedTemplate || !title.trim()) return;
    createMutation.mutate({
      title: title.trim(),
      template_id: selectedTemplate,
      source_file_ids: selectedFiles,
    });
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Создание отчёта</h1>

      {/* Steps indicator */}
      <div className="flex items-center gap-2">
        {[1, 2, 3].map((s) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={cn(
                'h-8 w-8 rounded-full flex items-center justify-center text-sm font-medium',
                s < step
                  ? 'bg-success text-success-foreground'
                  : s === step
                    ? 'bg-accent text-accent-foreground'
                    : 'bg-muted text-muted-foreground'
              )}
            >
              {s < step ? <Check className="h-4 w-4" /> : s}
            </div>
            <span className={cn('text-sm', s === step ? 'font-medium' : 'text-muted-foreground')}>
              {s === 1 ? 'Файлы' : s === 2 ? 'Шаблон' : 'Запуск'}
            </span>
            {s < 3 && <div className="w-8 h-px bg-border" />}
          </div>
        ))}
      </div>

      {/* Step 1 */}
      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Выберите исходные файлы</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {showUpload && (
              <FileUploadZone
                compact
                onUploadComplete={() => queryClient.invalidateQueries({ queryKey: ['files'] })}
              />
            )}
            <Button variant="outline" size="sm" onClick={() => setShowUpload(!showUpload)}>
              {showUpload ? 'Скрыть загрузку' : 'Загрузить новый файл'}
            </Button>

            {filesLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
              </div>
            ) : parsedFiles.length === 0 ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground p-4 rounded-md bg-muted/50">
                <AlertCircle className="h-4 w-4" />
                Нет обработанных файлов. Загрузите файлы выше.
              </div>
            ) : (
              <div className="space-y-1 max-h-64 overflow-auto">
                {parsedFiles.map((f) => (
                  <label
                    key={f.id}
                    className={cn(
                      'flex items-center gap-3 rounded-md border p-3 cursor-pointer transition-colors',
                      selectedFiles.includes(f.id) ? 'border-accent bg-accent/5' : 'hover:bg-muted/30'
                    )}
                  >
                    <Checkbox
                      checked={selectedFiles.includes(f.id)}
                      onCheckedChange={() => toggleFile(f.id)}
                    />
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm flex-1 truncate">{f.filename}</span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(f.uploaded_at).toLocaleDateString('ru-RU')}
                    </span>
                  </label>
                ))}
              </div>
            )}

            <div className="flex justify-end">
              <Button
                onClick={() => setStep(2)}
                disabled={!canProceedStep1}
                className="bg-accent hover:bg-accent/90 text-accent-foreground"
              >
                Далее <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 2 */}
      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Выберите шаблон</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Поиск шаблона..."
                className="pl-9"
                value={templateSearch}
                onChange={(e) => setTemplateSearch(e.target.value)}
              />
            </div>

            {templatesLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}
              </div>
            ) : filteredTemplates.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">Шаблоны не найдены</p>
            ) : (
              <div className="space-y-2 max-h-72 overflow-auto">
                {filteredTemplates.map((t) => (
                  <div
                    key={t.id}
                    onClick={() => setSelectedTemplate(t.id)}
                    className={cn(
                      'rounded-md border p-3 cursor-pointer transition-colors',
                      selectedTemplate === t.id
                        ? 'border-accent bg-accent/5'
                        : 'hover:bg-muted/30'
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium">{t.name}</p>
                      <Badge variant="secondary" className="text-xs">v{t.version}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">{t.document_type}</p>
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(1)}>
                <ChevronLeft className="mr-1 h-4 w-4" /> Назад
              </Button>
              <Button
                onClick={() => setStep(3)}
                disabled={!canProceedStep2}
                className="bg-accent hover:bg-accent/90 text-accent-foreground"
              >
                Далее <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 3 */}
      {step === 3 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Настройки и запуск</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="title">Название отчёта *</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Введите название отчёта"
              />
            </div>

            <div className="rounded-md border p-4 space-y-3">
              <h4 className="text-sm font-medium">Сводка</h4>
              <div className="space-y-1 text-sm">
                <p>
                  <span className="text-muted-foreground">Файлов: </span>
                  <span className="font-medium">{selectedFiles.length}</span>
                </p>
                <p>
                  <span className="text-muted-foreground">Шаблон: </span>
                  <span className="font-medium">{selectedTemplateName}</span>
                </p>
              </div>
            </div>

            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(2)}>
                <ChevronLeft className="mr-1 h-4 w-4" /> Назад
              </Button>
              <Button
                onClick={handleCreate}
                disabled={!canSubmit || createMutation.isPending}
                className="bg-accent hover:bg-accent/90 text-accent-foreground"
              >
                {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Создать отчёт
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
