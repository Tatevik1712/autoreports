import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, File as FileIcon, X, CheckCircle, AlertCircle } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { uploadFile } from '@/api/files';
import { cn } from '@/lib/utils';

const ACCEPTED = {
  'application/pdf': ['.pdf'],
  'application/msword': ['.doc'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'application/vnd.ms-excel': ['.xls'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'text/plain': ['.txt'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
};

const MAX_SIZE = 50 * 1024 * 1024;

interface UploadItem {
  file: File;
  progress: number;
  status: 'uploading' | 'done' | 'error';
  error?: string;
}

interface FileUploadZoneProps {
  onUploadComplete?: () => void;
  compact?: boolean;
}

export function FileUploadZone({ onUploadComplete, compact }: FileUploadZoneProps) {
  const [uploads, setUploads] = useState<UploadItem[]>([]);

  const handleUpload = useCallback(
    async (files: File[]) => {
      const newUploads: UploadItem[] = files.map((file) => ({
        file,
        progress: 0,
        status: 'uploading' as const,
      }));
      setUploads((prev) => [...prev, ...newUploads]);

      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        try {
          await uploadFile(file, (progress) => {
            setUploads((prev) =>
              prev.map((u) => (u.file === file ? { ...u, progress } : u))
            );
          });
          setUploads((prev) =>
            prev.map((u) => (u.file === file ? { ...u, status: 'done', progress: 100 } : u))
          );
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'Ошибка загрузки';
          setUploads((prev) =>
            prev.map((u) => (u.file === file ? { ...u, status: 'error', error: msg } : u))
          );
        }
      }
      onUploadComplete?.();
    },
    [onUploadComplete]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: handleUpload,
    accept: ACCEPTED,
    maxSize: MAX_SIZE,
    onDropRejected: (rejections) => {
      const items: UploadItem[] = rejections.map((r) => ({
        file: r.file,
        progress: 0,
        status: 'error' as const,
        error: r.errors.map((e) => e.message).join(', '),
      }));
      setUploads((prev) => [...prev, ...items]);
    },
  });

  const removeUpload = (file: File) => {
    setUploads((prev) => prev.filter((u) => u.file !== file));
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} Б`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
  };

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className={cn(
          'border-2 border-dashed rounded-lg transition-colors cursor-pointer flex flex-col items-center justify-center gap-2 text-muted-foreground',
          compact ? 'p-4' : 'p-8',
          isDragActive
            ? 'border-accent bg-accent/5 text-accent'
            : 'border-border hover:border-accent/50'
        )}
      >
        <input {...getInputProps()} />
        <Upload className={cn(isDragActive ? 'text-accent' : '', compact ? 'h-5 w-5' : 'h-8 w-8')} />
        {!compact && (
          <>
            <p className="text-sm font-medium">
              {isDragActive ? 'Отпустите файлы здесь' : 'Перетащите файлы или нажмите для выбора'}
            </p>
            <p className="text-xs">PDF, DOC, DOCX, XLS, XLSX, TXT, PNG, JPG — до 50 МБ</p>
          </>
        )}
        {compact && (
          <p className="text-xs">
            {isDragActive ? 'Отпустите файлы' : 'Загрузить файл'}
          </p>
        )}
      </div>

      {uploads.length > 0 && (
        <div className="space-y-2">
          {uploads.map((u, idx) => (
            <div
              key={`${u.file.name}-${idx}`}
              className="flex items-center gap-3 rounded-md border bg-card p-2.5 text-sm"
            >
              <FileIcon className="h-4 w-4 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="truncate font-medium">{u.file.name}</p>
                <p className="text-xs text-muted-foreground">{formatSize(u.file.size)}</p>
                {u.status === 'uploading' && <Progress value={u.progress} className="mt-1 h-1" />}
                {u.status === 'error' && (
                  <p className="text-xs text-destructive mt-0.5">{u.error}</p>
                )}
              </div>
              {u.status === 'done' && <CheckCircle className="h-4 w-4 text-success shrink-0" />}
              {u.status === 'error' && <AlertCircle className="h-4 w-4 text-destructive shrink-0" />}
              <button onClick={() => removeUpload(u.file)} className="text-muted-foreground hover:text-foreground">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
