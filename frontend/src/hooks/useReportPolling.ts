import { useQuery } from '@tanstack/react-query';
import { getReport } from '@/api/reports';
import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import type { ReportStatus } from '@/types';

export function useReportPolling(reportId: string) {
  const prevStatus = useRef<ReportStatus | null>(null);

  const query = useQuery({
    queryKey: ['report', reportId],
    queryFn: () => getReport(reportId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'pending' || status === 'processing') return 3000;
      return false;
    },
  });

  useEffect(() => {
    const current = query.data?.status;
    if (
      current === 'done' &&
      prevStatus.current &&
      prevStatus.current !== 'done'
    ) {
      toast.success('Отчёт готов!');
    }
    if (current) prevStatus.current = current;
  }, [query.data?.status]);

  return query;
}
