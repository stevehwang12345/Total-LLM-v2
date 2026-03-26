import type React from 'react'
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
  ClipboardList,
  AlertTriangle,
  Wrench,
  BarChart3,
  Eye,
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
  { value: 'daily_log', label: '관제일지 (일간)', icon: ClipboardList },
  { value: 'incident', label: '사건보고서', icon: AlertTriangle },
  { value: 'equipment', label: '장비점검일지', icon: Wrench },
  { value: 'monthly', label: '월간보안보고서', icon: BarChart3 },
]

const REPORT_TYPE_LABELS: Record<string, string> = {
  daily_log: '관제일지',
  incident: '사건보고서',
  equipment: '장비점검일지',
  monthly: '월간보안보고서',
  daily: '일일 보고서',
  weekly: '주간 보고서',
  security: '보안보고서',
}

function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [reportType, setReportType] = useState('daily_log')
  const [isGenerating, setIsGenerating] = useState(false)
  const [paramDate, setParamDate] = useState('')
  const [paramAlarmId, setParamAlarmId] = useState('')
  const [paramYear, setParamYear] = useState(new Date().getFullYear())
  const [paramMonth, setParamMonth] = useState(new Date().getMonth() + 1)
  const [deleteTarget, setDeleteTarget] = useState<Report | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [previewReport, setPreviewReport] = useState<Report | null>(null)
  const [previewData, setPreviewData] = useState<Record<string, unknown> | null>(null)
  const [isLoadingPreview, setIsLoadingPreview] = useState(false)

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
      const params: Record<string, unknown> = { type: reportType }
      if (reportType === 'daily_log' || reportType === 'equipment') {
        if (paramDate) params.date = paramDate
      } else if (reportType === 'incident') {
        if (paramAlarmId) params.alarm_id = paramAlarmId
      } else if (reportType === 'monthly') {
        params.year = paramYear
        params.month = paramMonth
      }
      const res = await fetch('/api/reports/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      })
      if (!res.ok) throw new Error(`생성 실패: ${res.status}`)
      const typeLabel = REPORT_TYPES.find((t) => t.value === reportType)?.label
      toast.success('리포트 생성 요청 완료', { description: typeLabel })
      setGenerateOpen(false)
      setParamDate('')
      setParamAlarmId('')
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

  const handlePreview = async (report: Report) => {
    setPreviewReport(report)
    setPreviewData(null)
    setIsLoadingPreview(true)
    try {
      const res = await fetch(`/api/reports/${report.report_id}`)
      if (res.ok) {
        const data = await res.json()
        setPreviewData(data.data_snapshot || null)
      }
    } catch {
      // data_snapshot 없으면 PDF만 표시
    } finally {
      setIsLoadingPreview(false)
    }
  }

  const getTypeLabel = (type: string) =>
    REPORT_TYPE_LABELS[type] || REPORT_TYPES.find((t) => t.value === type)?.label || type

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
              <div className='space-y-4 py-4'>
                <div className='grid gap-2'>
                  <Label>보고서 유형</Label>
                  <Select value={reportType} onValueChange={setReportType}>
                    <SelectTrigger className='w-full'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {REPORT_TYPES.map((t) => {
                        const Icon = t.icon
                        return (
                          <SelectItem key={t.value} value={t.value}>
                            <div className='flex items-center gap-2'>
                              <Icon className='size-4 text-muted-foreground' />
                              {t.label}
                            </div>
                          </SelectItem>
                        )
                      })}
                    </SelectContent>
                  </Select>
                </div>

                {(reportType === 'daily_log' || reportType === 'equipment') && (
                  <div className='grid gap-2'>
                    <Label htmlFor='param-date'>
                      {reportType === 'daily_log' ? '관제 일자' : '점검 일자'}
                    </Label>
                    <Input
                      id='param-date'
                      type='date'
                      value={paramDate}
                      onChange={(e) => setParamDate(e.target.value)}
                    />
                  </div>
                )}

                {reportType === 'incident' && (
                  <div className='grid gap-2'>
                    <Label htmlFor='param-alarm-id'>관련 알람 ID</Label>
                    <Input
                      id='param-alarm-id'
                      type='text'
                      placeholder='예: ALM-20260326-001'
                      value={paramAlarmId}
                      onChange={(e) => setParamAlarmId(e.target.value)}
                    />
                  </div>
                )}

                {reportType === 'monthly' && (
                  <div className='grid grid-cols-2 gap-3'>
                    <div className='grid gap-2'>
                      <Label htmlFor='param-year'>연도</Label>
                      <Input
                        id='param-year'
                        type='number'
                        min={2020}
                        max={2030}
                        value={paramYear}
                        onChange={(e) => setParamYear(Number(e.target.value))}
                      />
                    </div>
                    <div className='grid gap-2'>
                      <Label htmlFor='param-month'>월</Label>
                      <Input
                        id='param-month'
                        type='number'
                        min={1}
                        max={12}
                        value={paramMonth}
                        onChange={(e) => setParamMonth(Number(e.target.value))}
                      />
                    </div>
                  </div>
                )}
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
                             onClick={() => handlePreview(report)}
                           >
                             <Eye className='size-4' />
                           </Button>
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

        <Dialog open={!!previewReport} onOpenChange={(open) => !open && setPreviewReport(null)}>
          <DialogContent className='max-w-4xl max-h-[90vh]'>
            <DialogHeader>
              <DialogTitle className='flex items-center gap-2'>
                <FileText className='size-5' />
                {previewReport?.title}
              </DialogTitle>
              <DialogDescription>
                {previewReport && getTypeLabel(previewReport.type)} ·{' '}
                {previewReport && new Date(previewReport.created_at).toLocaleString('ko-KR')}
              </DialogDescription>
            </DialogHeader>

            <Tabs defaultValue='pdf' className='mt-2'>
              <TabsList className='grid w-full grid-cols-2'>
                <TabsTrigger value='pdf'>PDF 미리보기</TabsTrigger>
                <TabsTrigger value='data'>데이터 미리보기</TabsTrigger>
              </TabsList>

              <TabsContent value='pdf' className='mt-3'>
                {previewReport && (
                  <iframe
                    src={previewReport.download_url || `/api/reports/${previewReport.report_id}/download`}
                    className='h-[65vh] w-full rounded-lg border'
                    title='보고서 PDF 미리보기'
                  />
                )}
              </TabsContent>

              <TabsContent value='data' className='mt-3'>
                {isLoadingPreview ? (
                  <div className='flex items-center justify-center py-20'>
                    <Loader2 className='size-6 animate-spin text-muted-foreground' />
                  </div>
                ) : previewData ? (
                  <div className='max-h-[65vh] overflow-y-auto space-y-4'>
                    <DataSnapshotView data={previewData} />
                  </div>
                ) : (
                  <div className='flex flex-col items-center justify-center gap-2 py-20 text-muted-foreground'>
                    <FileText className='size-10 opacity-50' />
                    <p>데이터 스냅샷이 없습니다</p>
                    <p className='text-xs'>PDF 미리보기 탭을 이용해주세요</p>
                  </div>
                )}
              </TabsContent>
            </Tabs>

            <DialogFooter>
              <Button variant='outline' onClick={() => setPreviewReport(null)}>
                닫기
              </Button>
              <Button onClick={() => previewReport && handleDownload(previewReport)}>
                <Download className='size-4' />
                다운로드
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

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

const SECTION_LABELS: Record<string, string> = {
  date: '일자',
  period: '기간',
  alarms: '알람 현황',
  devices: '장비 현황',
  analyses: '분석 현황',
  alarms_by_severity: '심각도별 알람',
  notes: '특이사항',
  total: '총 장비',
  online: '온라인',
  offline: '오프라인',
}

function DataSnapshotView({ data }: { data: Record<string, unknown> }) {
  const renderValue = (_key: string, value: unknown): React.ReactNode => {
    if (value === null || value === undefined)
      return <span className='text-muted-foreground'>-</span>
    if (typeof value === 'object' && !Array.isArray(value)) {
      return (
        <div className='rounded-md border p-3 space-y-1'>
          {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
            <div key={k} className='flex justify-between text-sm'>
              <span className='text-muted-foreground'>{SECTION_LABELS[k] || k}</span>
              <span className='font-medium'>{String(v)}</span>
            </div>
          ))}
        </div>
      )
    }
    if (Array.isArray(value)) {
      if (value.length === 0)
        return <span className='text-muted-foreground'>없음</span>
      if (typeof value[0] === 'object') {
        const keys = Object.keys(value[0] as Record<string, unknown>)
        return (
          <div className='overflow-x-auto'>
            <Table>
              <TableHeader>
                <TableRow>
                  {keys.map((k) => (
                    <TableHead key={k} className='text-xs'>
                      {SECTION_LABELS[k] || k}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {value.slice(0, 20).map((item) => (
                  <TableRow key={JSON.stringify(item)}>
                    {keys.map((k) => (
                      <TableCell key={k} className='text-xs'>
                        {String((item as Record<string, unknown>)[k] ?? '-')}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {value.length > 20 && (
              <p className='text-xs text-muted-foreground mt-1'>
                ... 외 {value.length - 20}건
              </p>
            )}
          </div>
        )
      }
      return <span>{value.join(', ')}</span>
    }
    return <span className='font-medium'>{String(value)}</span>
  }

  return (
    <>
      {Object.entries(data).map(([key, value]) => (
        <Card key={key}>
          <CardHeader className='py-3 px-4'>
            <CardTitle className='text-sm'>
              {SECTION_LABELS[key] || key}
            </CardTitle>
          </CardHeader>
          <CardContent className='px-4 pb-3'>
            {renderValue(key, value)}
          </CardContent>
        </Card>
      ))}
    </>
  )
}
