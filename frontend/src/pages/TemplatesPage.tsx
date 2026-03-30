import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getTemplates, getTemplate } from '@/api/templates';
import { useAuthStore } from '@/store/authStore';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Link } from 'react-router-dom';
import { BookTemplate, ChevronDown, ChevronUp, Plus } from 'lucide-react';
import type { TemplateRead } from '@/types';

export default function TemplatesPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => getTemplates(1, 50),
  });

  const { data: detail } = useQuery({
    queryKey: ['template', expandedId],
    queryFn: () => getTemplate(expandedId!),
    enabled: !!expandedId,
  });

  const templates = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Шаблоны</h1>
        {isAdmin && (
          <Button asChild size="sm" className="bg-accent hover:bg-accent/90 text-accent-foreground">
            <Link to="/admin/templates"><Plus className="mr-2 h-4 w-4" />Создать шаблон</Link>
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32" />)}
        </div>
      ) : templates.length === 0 ? (
        <p className="text-muted-foreground">Шаблоны не найдены</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {templates.map((t) => (
            <Card key={t.id} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <BookTemplate className="h-5 w-5 text-accent" />
                    <CardTitle className="text-base">{t.name}</CardTitle>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">v{t.version}</Badge>
                    {!t.is_active && <Badge variant="destructive" className="text-xs">Неактивен</Badge>}
                    {expandedId === t.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">{t.document_type}</p>
              </CardHeader>
              {expandedId === t.id && detail && (
                <CardContent className="space-y-3">
                  {detail.description && <p className="text-sm text-muted-foreground">{detail.description}</p>}
                  <div>
                    <h4 className="text-sm font-medium mb-2">Секции</h4>
                    <div className="space-y-1">
                      {(detail as TemplateRead).sections.map((s) => (
                        <div key={s.key} className="flex items-center gap-2 text-sm">
                          <span className="font-medium">{s.title}</span>
                          {s.required && <Badge variant="outline" className="text-[10px]">обязательная</Badge>}
                        </div>
                      ))}
                    </div>
                  </div>
                  {(detail as TemplateRead).rules && (detail as TemplateRead).rules!.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-1">Правила</h4>
                      <ul className="text-xs text-muted-foreground space-y-0.5 list-disc pl-4">
                        {(detail as TemplateRead).rules!.map((r, i) => <li key={i}>{r}</li>)}
                      </ul>
                    </div>
                  )}
                  {isAdmin && (
                    <Button asChild variant="outline" size="sm">
                      <Link to={`/admin/templates?edit=${t.id}`}>Редактировать</Link>
                    </Button>
                  )}
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
