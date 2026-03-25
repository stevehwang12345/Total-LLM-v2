import { useState, useEffect, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  FileBarChart,
  Plus,
  Download,
  Trash2,
  Loader2,
  FileText,
  Calendar,
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ConfirmDialog } from '@/components/confirm-dialog'

export const Route = createFileRoute('/_authenticated/reports/')({
  component: ReportsPage,
})

interface Report {
  report_id: string
  title: string
  type: string
  created_at: string
  status?: string
  download_url?: string
}

const REPORT_TYPES = [
  { value: 'daily', label: '일일 보고서' },
  { value: 'weekly', label: '주간 보고서' },
  { value: 'incident', label: '사건 보고서' },
]

function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [reportType, setReportType] = useState('daily')
  const [isGenerating, setIsGenerating] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Report | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const fetchReports = useCallback(async () => {
    try {
      const res = await fetch('/api/reports')
      if (res.ok) {
        const data = await res.json()
        setReports(Array.isArray(data) ? data : data.reports || [])
      }
    } catch {
      void 0
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchReports()
  }, [fetchReports])

  const handleGenerate = async () => {
    setIsGenerating(true)
    try {
      const res = await fetch('/api/reports/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: reportType }),
      })
      if (!res.ok) throw new Error(`생성 실패: ${res.status}`)
      const typeLabel = REPORT_TYPES.find((t) => t.value === reportType)?.label
      toast.success('리포트 생성 요청 완료', { description: typeLabel })
      setGenerateOpen(false)
      fetchReports()
    } catch (err) {
      const msg = err instanceof Error ? err.message : '리포트 생성 오류'
      toast.error('리포트 생성 실패', { description: msg })
    } finally {
      setIsGenerating(false)
    }
  }

  const handleDownload = (report: Report) => {
    if (report.download_url) {
      window.open(report.download_url, '_blank')
    } else {
      window.open(`/api/reports/${report.report_id}/download`, '_blank')
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      const res = await fetch(`/api/reports/${deleteTarget.report_id}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error('삭제 실패')
      toast.success('리포트 삭제 완료')
      setDeleteTarget(null)
      fetchReports()
    } catch {
      toast.error('리포트 삭제 실패')
    } finally {
      setIsDeleting(false)
    }
  }

  const getTypeLabel = (type: string) =>
    REPORT_TYPES.find((t) => t.value === type)?.label || type

  return (
    <>
      <Header fixed>
        <div className='flex w-full items-center justify-between'>
          <div className='flex items-center gap-2'>
            <FileBarChart className='size-5 text-primary' />
            <h1 className='text-lg font-semibold'>리포트</h1>
            <Badge variant='secondary'>{reports.length}개</Badge>
          </div>
          <Dialog open={generateOpen} onOpenChange={setGenerateOpen}>
            <DialogTrigger asChild>
              <Button size='sm'>
                <Plus className='size-4' />
                리포트 생성
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>리포트 생성</DialogTitle>
                <DialogDescription>
                  생성할 리포트 유형을 선택하세요
                </DialogDescription>
              </DialogHeader>
              <div className='py-4'>
                <Select value={reportType} onValueChange={setReportType}>
                  <SelectTrigger className='w-full'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {REPORT_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <DialogFooter>
                <Button
                  variant='outline'
                  onClick={() => setGenerateOpen(false)}
                >
                  취소
                </Button>
                <Button onClick={handleGenerate} disabled={isGenerating}>
                  {isGenerating ? (
                    <>
                      <Loader2 className='size-4 animate-spin' />
                      생성 중...
                    </>
                  ) : (
                    '생성'
                  )}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </Header>
      <Main>
        <Card>
          <CardHeader>
            <CardTitle>리포트 목록</CardTitle>
            <CardDescription>
              생성된 보안 리포트를 확인하고 다운로드하세요
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className='flex items-center justify-center py-10'>
                <Loader2 className='size-6 animate-spin text-muted-foreground' />
              </div>
            ) : reports.length === 0 ? (
              <div className='flex flex-col items-center justify-center gap-3 py-16'>
                <FileBarChart className='size-12 text-muted-foreground/50' />
                <p className='text-muted-foreground'>생성된 리포트가 없습니다</p>
                <Button size='sm' onClick={() => setGenerateOpen(true)}>
                  <Plus className='size-4' />
                  리포트 생성
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>제목</TableHead>
                    <TableHead>유형</TableHead>
                    <TableHead>생성일</TableHead>
                    <TableHead>상태</TableHead>
                    <TableHead className='text-right'>작업</TableHead>
                  </TableRow>
                </TableHeader>
                 <TableBody>
                   {reports.map((report) => (
                     <TableRow key={report.report_id}>
                      <TableCell>
                        <div className='flex items-center gap-2'>
                          <FileText className='size-4 text-muted-foreground' />
                          <span className='text-sm font-medium'>
                            {report.title}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant='secondary'>
                          {getTypeLabel(report.type)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className='flex items-center gap-1.5 text-xs text-muted-foreground'>
                          <Calendar className='size-3' />
                          {new Date(report.created_at).toLocaleString('ko-KR')}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            report.status === 'completed' || !report.status
                              ? 'default'
                              : 'secondary'
                          }
                        >
                          {report.status === 'completed' || !report.status
                            ? '완료'
                            : '생성 중'}
                        </Badge>
                      </TableCell>
                       <TableCell>
                         <div className='flex items-center justify-end gap-1'>
                           <Button
                             variant='ghost'
                             size='icon'
                             className='size-8'
                             onClick={() => handleDownload(report)}
                           >
                             <Download className='size-4' />
                           </Button>
                          <Button
                            variant='ghost'
                            size='icon'
                            className='size-8 text-destructive hover:text-destructive'
                            onClick={() => setDeleteTarget(report)}
                          >
                            <Trash2 className='size-4' />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <ConfirmDialog
          open={!!deleteTarget}
          onOpenChange={(open) => !open && setDeleteTarget(null)}
          title='리포트 삭제'
          desc={`"${deleteTarget?.title}" 리포트를 삭제하시겠습니까?`}
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
