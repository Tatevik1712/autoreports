import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getTemplates, createTemplate, updateTemplate, deleteTemplate, getTemplate } from '@/api/templates';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
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
import { toast } from 'sonner';
import { Plus, Edit, Trash2, Loader2 } from 'lucide-react';
import type { CreateTemplateRequest } from '@/types';

const emptyForm: CreateTemplateRequest = {
  name: '',
  slug: '',
  document_type: '',
  description: '',
  sections: [],
  schema: {},
  rules: [],
};

export default function AdminTemplatesPage() {
  const queryClient = useQueryClient();
  const [showDialog, setShowDialog] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState<CreateTemplateRequest>(emptyForm);
  const [schemaText, setSchemaText] = useState('{}');
  const [sectionsText, setSectionsText] = useState('[]');
  const [rulesText, setRulesText] = useState('[]');

  const { data, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => getTemplates(1, 100),
  });

  const createMut = useMutation({
    mutationFn: createTemplate,
    onSuccess: () => {
      toast.success('Шаблон создан');
      queryClient.invalidateQueries({ queryKey: ['templates'] });
      setShowDialog(false);
    },
    onError: () => toast.error('Ошибка создания шаблона'),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CreateTemplateRequest> }) =>
      updateTemplate(id, data),
    onSuccess: () => {
      toast.success('Шаблон обновлён');
      queryClient.invalidateQueries({ queryKey: ['templates'] });
      setShowDialog(false);
      setEditId(null);
    },
    onError: () => toast.error('Ошибка обновления'),
  });

  const deleteMut = useMutation({
    mutationFn: deleteTemplate,
    onSuccess: () => {
      toast.success('Шаблон деактивирован');
      queryClient.invalidateQueries({ queryKey: ['templates'] });
      setDeleteId(null);
    },
  });

  const openCreate = () => {
    setForm(emptyForm);
    setSchemaText('{}');
    setSectionsText('[]');
    setRulesText('[]');
    setEditId(null);
    setShowDialog(true);
  };

  const openEdit = async (id: string) => {
    const t = await getTemplate(id);
    setForm({
      name: t.name,
      slug: t.slug,
      document_type: t.document_type,
      description: t.description || '',
      sections: t.sections,
      schema: t.schema,
      rules: t.rules || [],
    });
    setSchemaText(JSON.stringify(t.schema, null, 2));
    setSectionsText(JSON.stringify(t.sections, null, 2));
    setRulesText(JSON.stringify(t.rules || [], null, 2));
    setEditId(id);
    setShowDialog(true);
  };

  const handleSubmit = () => {
    try {
      const data: CreateTemplateRequest = {
        ...form,
        schema: JSON.parse(schemaText),
        sections: JSON.parse(sectionsText),
        rules: JSON.parse(rulesText),
      };
      if (editId) {
        updateMut.mutate({ id: editId, data });
      } else {
        createMut.mutate(data);
      }
    } catch {
      toast.error('Ошибка в JSON. Проверьте формат.');
    }
  };

  const templates = data?.items ?? [];
  const isPending = createMut.isPending || updateMut.isPending;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Управление шаблонами</h1>
        <Button size="sm" onClick={openCreate} className="bg-accent hover:bg-accent/90 text-accent-foreground">
          <Plus className="mr-2 h-4 w-4" />Создать шаблон
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}
        </div>
      ) : templates.length === 0 ? (
        <p className="text-muted-foreground">Шаблонов нет</p>
      ) : (
        <div className="space-y-3">
          {templates.map((t) => (
            <Card key={t.id}>
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <p className="font-medium">{t.name}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant="secondary" className="text-xs">v{t.version}</Badge>
                    <span className="text-xs text-muted-foreground">{t.document_type}</span>
                    {!t.is_active && <Badge variant="destructive" className="text-xs">Неактивен</Badge>}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => openEdit(t.id)}>
                    <Edit className="h-4 w-4" />
                  </Button>
                  <Button variant="outline" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => setDeleteId(t.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>{editId ? 'Редактировать шаблон' : 'Новый шаблон'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Название</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label>Slug</Label>
                <Input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Тип документа</Label>
              <Input value={form.document_type} onChange={(e) => setForm({ ...form, document_type: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label>Описание</Label>
              <Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label>Секции (JSON)</Label>
              <Textarea className="font-mono text-xs min-h-[120px]" value={sectionsText} onChange={(e) => setSectionsText(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Schema (JSON)</Label>
              <Textarea className="font-mono text-xs min-h-[120px]" value={schemaText} onChange={(e) => setSchemaText(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Правила (JSON массив строк)</Label>
              <Textarea className="font-mono text-xs min-h-[80px]" value={rulesText} onChange={(e) => setRulesText(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>Отмена</Button>
            <Button onClick={handleSubmit} disabled={isPending} className="bg-accent hover:bg-accent/90 text-accent-foreground">
              {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {editId ? 'Сохранить' : 'Создать'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Деактивировать шаблон?</AlertDialogTitle>
            <AlertDialogDescription>Шаблон будет деактивирован.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground" onClick={() => deleteId && deleteMut.mutate(deleteId)}>
              Деактивировать
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
