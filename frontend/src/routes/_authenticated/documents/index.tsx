import { useState, useEffect, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useDropzone } from 'react-dropzone'
import {
  FileText,
  Upload,
  Trash2,
  Loader2,
  File,
  FileType2,
  HardDrive,
} from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'

export const Route = createFileRoute('/_authenticated/documents/')({
  component: DocumentsPage,
})

interface Document {
  id: string
  filename: string
  size: number
  uploaded_at: string
  content_type?: string
  chunk_count?: number
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getFileIcon(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase()
  if (ext === 'pdf') return <FileType2 className='size-4 text-red-500' />
  if (ext === 'md') return <FileText className='size-4 text-blue-500' />
  if (ext === 'docx' || ext === 'doc') return <File className='size-4 text-blue-600' />
  return <FileText className='size-4 text-muted-foreground' />
}

function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<Document | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const fetchDocuments = useCallback(async () => {
    try {
      const res = await fetch('/api/documents')
      if (res.ok) {
        const data = await res.json()
        setDocuments(Array.isArray(data) ? data : data.documents || [])
      }
    } catch {
      void 0
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  const onDrop = useCallback(
    async (accepted: File[]) => {
      if (accepted.length === 0) return
      setUploading(true)
      setUploadProgress(0)

      let completed = 0
      for (const file of accepted) {
        try {
          const formData = new FormData()
          formData.append('file', file)

          const res = await fetch('/api/documents/upload', {
            method: 'POST',
            body: formData,
          })

          if (!res.ok) throw new Error(`업로드 실패: ${file.name}`)

          completed++
          setUploadProgress(Math.round((completed / accepted.length) * 100))
          toast.success('업로드 완료', { description: file.name })
        } catch (err) {
          const msg = err instanceof Error ? err.message : '업로드 오류'
          toast.error(msg)
        }
      }

      setUploading(false)
      setUploadProgress(0)
      fetchDocuments()
    },
    [fetchDocuments]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/markdown': ['.md'],
      'text/plain': ['.txt'],
    },
    multiple: true,
  })

  const handleDelete = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      const res = await fetch(`/api/documents/${deleteTarget.id}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error('삭제 실패')
      toast.success('문서 삭제 완료', { description: deleteTarget.filename })
      setDeleteTarget(null)
      fetchDocuments()
    } catch {
      toast.error('문서 삭제 실패')
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <>
      <Header fixed>
        <div className='flex items-center gap-2'>
          <FileText className='size-5 text-primary' />
          <h1 className='text-lg font-semibold'>문서 관리</h1>
          <Badge variant='secondary'>{documents.length}개</Badge>
        </div>
      </Header>
      <Main>
        <div className='grid gap-6 lg:grid-cols-3'>
          <div className='lg:col-span-1'>
            <Card>
              <CardHeader>
                <CardTitle>문서 업로드</CardTitle>
                <CardDescription>
                  RAG 시스템에 사용할 문서를 업로드하세요
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div
                  {...getRootProps()}
                  className={cn(
                    'flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 transition-colors',
                    isDragActive
                      ? 'border-primary bg-primary/5'
                      : 'border-muted-foreground/25 hover:border-primary/50'
                  )}
                >
                  <input {...getInputProps()} />
                  <div className='flex size-12 items-center justify-center rounded-xl bg-muted'>
                    <Upload className='size-6 text-muted-foreground' />
                  </div>
                  <div className='text-center'>
                    <p className='text-sm font-medium'>
                      {isDragActive
                        ? '여기에 놓으세요'
                        : '클릭하거나 드래그하여 업로드'}
                    </p>
                    <p className='mt-1 text-xs text-muted-foreground'>
                      PDF, DOCX, MD, TXT 형식 지원
                    </p>
                  </div>
                </div>
                {uploading && (
                  <div className='mt-4 space-y-2'>
                    <div className='flex items-center justify-between text-sm'>
                      <span className='flex items-center gap-2'>
                        <Loader2 className='size-3.5 animate-spin' />
                        업로드 중...
                      </span>
                      <span>{uploadProgress}%</span>
                    </div>
                    <div className='h-2 overflow-hidden rounded-full bg-muted'>
                      <div
                        className='h-full rounded-full bg-primary transition-all'
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <Card className='lg:col-span-2'>
            <CardHeader>
              <div className='flex items-center gap-2'>
                <HardDrive className='size-4 text-muted-foreground' />
                <CardTitle>문서 목록</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className='flex items-center justify-center py-10'>
                  <Loader2 className='size-6 animate-spin text-muted-foreground' />
                </div>
              ) : documents.length === 0 ? (
                <div className='flex flex-col items-center justify-center gap-3 py-10'>
                  <FileText className='size-10 text-muted-foreground/50' />
                  <p className='text-sm text-muted-foreground'>
                    업로드된 문서가 없습니다
                  </p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>파일명</TableHead>
                      <TableHead>크기</TableHead>
                      <TableHead>업로드 일시</TableHead>
                      <TableHead className='text-right'>작업</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documents.map((doc) => (
                      <TableRow key={doc.id}>
                        <TableCell>
                          <div className='flex items-center gap-2'>
                            {getFileIcon(doc.filename)}
                            <span className='text-sm font-medium'>
                              {doc.filename}
                            </span>
                            {doc.chunk_count && (
                              <Badge variant='secondary' className='text-xs'>
                                {doc.chunk_count} 청크
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className='text-sm text-muted-foreground'>
                          {formatFileSize(doc.size)}
                        </TableCell>
                        <TableCell className='text-xs text-muted-foreground'>
                          {new Date(doc.uploaded_at).toLocaleString('ko-KR')}
                        </TableCell>
                        <TableCell className='text-right'>
                          <Button
                            variant='ghost'
                            size='icon'
                            className='size-8 text-destructive hover:text-destructive'
                            onClick={() => setDeleteTarget(doc)}
                          >
                            <Trash2 className='size-4' />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>

        <ConfirmDialog
          open={!!deleteTarget}
          onOpenChange={(open) => !open && setDeleteTarget(null)}
          title='문서 삭제'
          desc={`"${deleteTarget?.filename}" 문서를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`}
          confirmText='삭제'
          cancelBtnText='취소'
          destructive
          isLoading={isDeleting}
          handleConfirm={handleDelete}
        />
      </Main>
    </>
  )
}
