import { type ReportStatus } from '@/types';
import { Clock, Loader2, CheckCircle, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const statusConfig: Record<ReportStatus, { label: string; icon: typeof Clock; className: string }> = {
  pending: { label: 'Ожидает', icon: Clock, className: 'status-pending' },
  processing: { label: 'Обработка', icon: Loader2, className: 'status-processing animate-pulse-processing' },
  done: { label: 'Готов', icon: CheckCircle, className: 'status-done' },
  error: { label: 'Ошибка', icon: XCircle, className: 'status-error' },
};

export function StatusBadge({ status }: { status: ReportStatus }) {
  const config = statusConfig[status];
  const Icon = config.icon;
  return (
    <Badge variant="outline" className={cn('gap-1 border-0 font-medium', config.className)}>
      <Icon className={cn('h-3 w-3', status === 'processing' && 'animate-spin')} />
      {config.label}
    </Badge>
  );
}
