import { useState, useEffect, useCallback, useRef } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useDropzone } from 'react-dropzone'
import {
  Camera,
  Upload,
  Loader2,
  Image as ImageIcon,
  Video,
  Film,
  AlertTriangle,
  X,
  ChevronDown,
  Copy,
  Check,
  MapPin,
  Clock,
  Shield,
  Building2,
  PersonStanding,
  User,
  Globe,
  FileText,
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
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Separator } from '@/components/ui/separator'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

export const Route = createFileRoute('/_authenticated/analysis/')({
  component: AnalysisPage,
})

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface QAResults {
  q1_scene: string
  q2_behavior: string
  q3_entities: string
  q4_context: string
}

const EMPTY_QA_RESULTS: QAResults = {
  q1_scene: '',
  q2_behavior: '',
  q3_entities: '',
  q4_context: '',
}

interface AnalysisResult {
  analysis_id: string
  filename: string
  location: string | null
  incident_type: string
  incident_type_en: string
  severity: string
  risk_level: number
  confidence: number
  qa_results: QAResults
  report: string
  recommended_actions: string[]
  sop_reference: string | null
  content_type?: string
  media_type?: string
}

interface AnalysisHistoryItem {
  analysis_id: string
  filename: string
  location: string | null
  incident_type: string
  severity: string
  risk_level: number
  confidence: number
  created_at: string
  content_type?: string
  media_type?: string
}

/* ------------------------------------------------------------------ */
/*  Risk Level Config                                                  */
/* ------------------------------------------------------------------ */

interface RiskConfig {
  label: string
  labelEn: string
  emoji: string
  bgClass: string
  textClass: string
  badgeClass: string
  pulse?: boolean
}

const RISK_CONFIG: Record<number, RiskConfig> = {
  1: {
    label: '정보',
    labelEn: 'INFO',
    emoji: '🟢',
    bgClass: 'bg-zinc-500/10 dark:bg-zinc-400/10 border-zinc-500/20',
    textClass: 'text-zinc-700 dark:text-zinc-300',
    badgeClass: 'bg-zinc-500/15 text-zinc-700 dark:text-zinc-400 border-zinc-500/20',
  },
  2: {
    label: '낮음',
    labelEn: 'LOW',
    emoji: '🔵',
    bgClass: 'bg-blue-500/10 dark:bg-blue-400/10 border-blue-500/20',
    textClass: 'text-blue-700 dark:text-blue-300',
    badgeClass: 'bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/20',
  },
  3: {
    label: '중간',
    labelEn: 'MEDIUM',
    emoji: '🟡',
    bgClass: 'bg-yellow-500/10 dark:bg-yellow-400/10 border-yellow-500/20',
    textClass: 'text-yellow-700 dark:text-yellow-300',
    badgeClass: 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 border-yellow-500/20',
  },
  4: {
    label: '높음',
    labelEn: 'HIGH',
    emoji: '🟠',
    bgClass: 'bg-orange-500/10 dark:bg-orange-400/10 border-orange-500/20',
    textClass: 'text-orange-700 dark:text-orange-300',
    badgeClass: 'bg-orange-500/15 text-orange-700 dark:text-orange-400 border-orange-500/20',
  },
  5: {
    label: '매우높음',
    labelEn: 'CRITICAL',
    emoji: '🔴',
    bgClass: 'bg-red-500/10 dark:bg-red-400/10 border-red-500/20',
    textClass: 'text-red-700 dark:text-red-300',
    badgeClass: 'bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/20',
    pulse: true,
  },
}

function getRiskConfig(level: number): RiskConfig {
  return RISK_CONFIG[level] ?? RISK_CONFIG[1]
}

/* ------------------------------------------------------------------ */
/*  Media Type Helpers                                                  */
/* ------------------------------------------------------------------ */

function isVideoFile(file: File): boolean {
  return file.type.startsWith('video/')
}

function isVideoMedia(item: { content_type?: string; media_type?: string }): boolean {
  return item.media_type === 'video' || item.content_type?.startsWith('video/') === true
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function RiskLevelBadge({ riskLevel }: { riskLevel: number }) {
  const config = getRiskConfig(riskLevel)
  return (
    <Badge variant='outline' className={config.badgeClass}>
      {config.emoji} {config.label}
    </Badge>
  )
}

function ThreatBanner({ result }: { result: AnalysisResult }) {
  const config = getRiskConfig(result.risk_level)
  return (
    <div
      className={cn(
        'rounded-lg border p-4 text-center',
        config.bgClass,
        config.pulse && 'animate-pulse'
      )}
    >
      <p className={cn('text-2xl font-bold tracking-wide', config.textClass)}>
        {config.emoji} LEVEL {result.risk_level} — {config.label} ({config.labelEn})
      </p>
    </div>
  )
}

function SummaryCard({ result }: { result: AnalysisResult }) {
  return (
    <Card>
      <CardContent className='flex items-center justify-between gap-4 py-4'>
        <div className='flex items-center gap-3'>
          <Shield className='size-5 text-muted-foreground' />
          <div>
            <p className='text-sm font-semibold'>{result.incident_type}</p>
            <p className='text-xs text-muted-foreground'>{result.incident_type_en}</p>
          </div>
        </div>
        <Separator orientation='vertical' className='h-8' />
        <div className='text-center'>
          <p className='text-2xl font-bold tabular-nums'>
            {(result.confidence * 100).toFixed(1)}%
          </p>
          <p className='text-xs text-muted-foreground'>신뢰도</p>
        </div>
      </CardContent>
    </Card>
  )
}

const QA_ITEMS: Array<{
  key: keyof QAResults
  icon: typeof Building2
  title: string
}> = [
  { key: 'q1_scene', icon: Building2, title: '장면 분석' },
  { key: 'q2_behavior', icon: PersonStanding, title: '행동 분석' },
  { key: 'q3_entities', icon: User, title: '객체·인물 분석' },
  { key: 'q4_context', icon: Globe, title: '환경·맥락 분석' },
]

function QAAccordion({ qaResults }: { qaResults: QAResults }) {
  const [openItems, setOpenItems] = useState<Set<string>>(new Set())

  const toggle = (key: string) => {
    setOpenItems((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <Card>
      <CardHeader className='pb-3'>
        <CardTitle className='text-base'>🔍 상세 분석 결과</CardTitle>
      </CardHeader>
      <CardContent className='space-y-1 pt-0'>
        {QA_ITEMS.map(({ key, icon: Icon, title }) => {
          const isOpen = openItems.has(key)
          const content = qaResults[key]
          return (
            <div key={key} className='rounded-md border'>
              <button
                type='button'
                onClick={() => toggle(key)}
                className='flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50'
              >
                <Icon className='size-4 shrink-0 text-muted-foreground' />
                <span className='flex-1 text-sm font-medium'>{title}</span>
                <ChevronDown
                  className={cn(
                    'size-4 text-muted-foreground transition-transform duration-200',
                    isOpen && 'rotate-180'
                  )}
                />
              </button>
              {isOpen && (
                <div className='border-t bg-muted/30 px-4 py-3'>
                  <p className='text-sm leading-relaxed text-foreground/80 whitespace-pre-wrap'>
                    {content}
                  </p>
                </div>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

function SecurityReport({ report }: { report: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(report)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('클립보드 복사 실패')
    }
  }

  return (
    <Card>
      <CardHeader className='flex-row items-center justify-between pb-3'>
        <CardTitle className='text-base'>📋 보안 분석 보고서</CardTitle>
        <Button
          variant='outline'
          size='sm'
          className='h-7 gap-1.5 text-xs'
          onClick={handleCopy}
        >
          {copied ? (
            <Check className='size-3' />
          ) : (
            <Copy className='size-3' />
          )}
          {copied ? '복사됨' : '복사'}
        </Button>
      </CardHeader>
      <CardContent className='pt-0'>
        <div className='rounded-md border bg-muted/30 p-4'>
          <pre className='whitespace-pre-wrap text-sm leading-relaxed font-mono text-foreground/80'>
            {report}
          </pre>
        </div>
      </CardContent>
    </Card>
  )
}

function RecommendedActions({
  actions,
  sopReference,
}: {
  actions: string[]
  sopReference: string | null
}) {
  if (actions.length === 0 && !sopReference) return null
  return (
    <Card>
      <CardHeader className='pb-3'>
        <CardTitle className='text-base'>⚠️ 권장 조치</CardTitle>
      </CardHeader>
      <CardContent className='pt-0'>
        <div className='flex flex-wrap gap-2'>
          {actions.map((action) => (
            <Badge
              key={action}
              variant='secondary'
              className='text-xs py-1 px-2.5'
            >
              {action}
            </Badge>
          ))}
        </div>
        {sopReference && (
          <div className='mt-3 rounded-md border border-dashed p-3'>
            <p className='text-xs text-muted-foreground'>
              <FileText className='mr-1 inline size-3' />
              SOP 참조: <span className='font-medium text-foreground'>{sopReference}</span>
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ------------------------------------------------------------------ */
/*  Loading Steps                                                      */
/* ------------------------------------------------------------------ */

const IMAGE_ANALYSIS_STEPS = [
  '장면 분석',
  '행동 분석',
  '객체·인물 분석',
  '환경·맥락 분석',
  '보고서 생성',
] as const

const VIDEO_ANALYSIS_STEPS = [
  '프레임 추출',
  '장면 분석',
  '행동 분석',
  '객체·인물 분석',
  '환경·맥락 분석',
  '보고서 생성',
] as const

function AnalysisProgress({ elapsed, mediaType }: { elapsed: number; mediaType: 'image' | 'video' }) {
  const steps = mediaType === 'video' ? VIDEO_ANALYSIS_STEPS : IMAGE_ANALYSIS_STEPS
  const estimatedTime = mediaType === 'video' ? '약 30~60초 소요' : '약 15~30초 소요'
  const completedSteps = Math.min(
    Math.floor(elapsed / 4),
    steps.length
  )

  return (
    <div className='mt-4 space-y-2 rounded-md border bg-muted/30 p-4'>
      <div className='mb-3 flex items-center gap-2'>
        <Loader2 className='size-4 animate-spin text-primary' />
        <p className='text-sm font-medium'>분석 중... ({estimatedTime})</p>
      </div>
      {steps.map((step, i) => {
        const done = i < completedSteps
        const active = i === completedSteps
        return (
          <div
            key={step}
            className={cn(
              'flex items-center gap-2 text-sm transition-opacity',
              done
                ? 'text-green-600 dark:text-green-400'
                : active
                  ? 'text-foreground'
                  : 'text-muted-foreground/50'
            )}
          >
            {done ? (
              <Check className='size-3.5' />
            ) : active ? (
              <Loader2 className='size-3.5 animate-spin' />
            ) : (
              <span className='size-3.5' />
            )}
            {step}
          </div>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  History Table                                                      */
/* ------------------------------------------------------------------ */

function HistoryTable({
  history,
  onRowClick,
}: {
  history: AnalysisHistoryItem[]
  onRowClick?: (id: string) => void
}) {
  return (
    <Card>
      <CardHeader>
        <div className='flex items-center gap-2'>
          <AlertTriangle className='size-4 text-muted-foreground' />
          <CardTitle>분석 이력</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        {history.length === 0 ? (
          <p className='py-8 text-center text-sm text-muted-foreground'>
            분석 이력이 없습니다
          </p>
        ) : (
          <div className='overflow-x-auto'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className='w-14'>미디어</TableHead>
                  <TableHead>시각</TableHead>
                  <TableHead>위치</TableHead>
                  <TableHead>이벤트 유형</TableHead>
                  <TableHead>위험 수준</TableHead>
                  <TableHead>신뢰도</TableHead>
                  <TableHead>파일명</TableHead>
                </TableRow>
              </TableHeader>
               <TableBody>
                 {history.map((item) => (
                   <TableRow
                     key={item.analysis_id}
                     onClick={() => onRowClick?.(item.analysis_id)}
                     className={cn(onRowClick && 'cursor-pointer hover:bg-muted/50')}
                   >
                     <TableCell className='w-14 py-1'>
                        {isVideoMedia(item) ? (
                          <div className='flex size-10 items-center justify-center rounded border bg-muted'>
                            <Film className='size-5 text-muted-foreground' />
                          </div>
                        ) : (
                          <img
                            src={`/api/analysis/${item.analysis_id}/image`}
                            alt={item.filename}
                            className='size-10 rounded border object-cover'
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = 'none'
                            }}
                          />
                        )}
                      </TableCell>
                     <TableCell className='text-xs whitespace-nowrap'>
                       {new Date(item.created_at).toLocaleString('ko-KR')}
                     </TableCell>
                    <TableCell className='text-sm'>
                      {item.location || '—'}
                    </TableCell>
                    <TableCell className='text-sm font-medium'>
                      {item.incident_type}
                    </TableCell>
                    <TableCell>
                      <RiskLevelBadge riskLevel={item.risk_level} />
                    </TableCell>
                    <TableCell className='text-sm tabular-nums'>
                      {(item.confidence * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell className='max-w-[160px] truncate text-xs text-muted-foreground'>
                      {item.filename}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

function AnalysisPage() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [location, setLocation] = useState('')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [history, setHistory] = useState<AnalysisHistoryItem[]>([])
  const [detail, setDetail] = useState<AnalysisResult | null>(null)
  const [currentTime, setCurrentTime] = useState(new Date())
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  /* Clock */
  useEffect(() => {
    const id = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  /* Elapsed timer for loading progress */
  useEffect(() => {
    if (isAnalyzing) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed((e) => e + 1), 1000)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isAnalyzing])

  /* Fetch history */
  const openDetail = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/analysis/${id}`)
      if (!res.ok) {
        toast.error('상세 이력 조회 실패', {
          description: `응답 코드: ${res.status}`,
        })
        return
      }
      const data = await res.json()
      setDetail({
        ...data,
        incident_type: data.incident_type || data.result?.incident_type || '정상활동',
        incident_type_en: data.incident_type_en || data.result?.incident_type_en || 'Normal',
        severity: data.severity || data.result?.severity || '정보',
        risk_level: data.risk_level || data.result?.risk_level || 1,
        confidence: data.confidence || data.result?.confidence || 0.5,
        qa_results: {
          ...EMPTY_QA_RESULTS,
          ...(data.qa_results || data.result?.qa_results || {}),
        },
        report: data.report || data.result?.report || '',
        recommended_actions: data.recommended_actions || data.result?.recommended_actions || [],
        sop_reference: data.sop_reference || data.result?.sop_reference || null,
      } as AnalysisResult)
    } catch (err) {
      const message = err instanceof Error ? err.message : '상세 이력 조회 중 오류 발생'
      toast.error('상세 이력 조회 실패', { description: message })
    }
  }, [])

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/analysis')
      if (res.ok) {
        const data: unknown = await res.json()
        setHistory(Array.isArray(data) ? (data as AnalysisHistoryItem[]) : [])
      }
    } catch {
      void 0
    }
  }, [])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  /* Dropzone */
  const onDrop = useCallback((accepted: File[]) => {
    const f = accepted[0]
    if (!f) return
    setFile(f)
    setResult(null)
    const url = URL.createObjectURL(f)
    setPreview(url)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.jpg', '.jpeg', '.png', '.bmp', '.webp'],
      'video/mp4': ['.mp4'],
    },
    maxFiles: 1,
    multiple: false,
  })

  /* Analysis */
  const handleAnalyze = async () => {
    if (!file) return
    setIsAnalyzing(true)
    setResult(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      if (location.trim()) {
        formData.append('location', location.trim())
      }
      const res = await fetch('/api/analysis/upload', {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error(`분석 실패: ${res.status}`)
      const data = (await res.json()) as AnalysisResult
      setResult(data)
      toast.success('분석 완료', {
        description: `${data.incident_type} (${data.incident_type_en})`,
      })
      fetchHistory()
    } catch (err) {
      const message = err instanceof Error ? err.message : '분석 중 오류 발생'
      toast.error('분석 실패', { description: message })
    } finally {
      setIsAnalyzing(false)
    }
  }

  const clearFile = () => {
    setFile(null)
    setPreview(null)
    setResult(null)
    setLocation('')
  }

  return (
    <>
      {/* ── Header ── */}
      <Header fixed>
        <div className='flex flex-1 items-center justify-between'>
          <div className='flex items-center gap-2'>
            <Camera className='size-5 text-primary' />
            <div>
              <h1 className='text-lg font-semibold leading-tight'>
                CCTV 영상 분석
              </h1>
              <p className='text-xs text-muted-foreground'>
                AI 기반 물리보안 위협 감지
              </p>
            </div>
          </div>
          <div className='flex items-center gap-1.5 text-sm tabular-nums text-muted-foreground'>
            <Clock className='size-3.5' />
            {currentTime.toLocaleString('ko-KR')}
          </div>
        </div>
      </Header>

      {/* ── Content ── */}
      <Main fluid>
        <div className='grid gap-6 lg:grid-cols-[400px_1fr]'>
          {/* ── Left Panel: Upload ── */}
          <div className='flex flex-col gap-4'>
            <Card>
              <CardHeader>
                <CardTitle>미디어 업로드</CardTitle>
                <CardDescription>
                  분석할 CCTV 이미지 또는 영상을 업로드하세요
                </CardDescription>
              </CardHeader>
              <CardContent className='space-y-4'>
                {/* Drop zone */}
                {file && isVideoFile(file) ? (
                  <div className='relative'>
                    <video
                      src={preview ?? undefined}
                      controls
                      className='w-full rounded-lg border object-contain'
                      style={{ maxHeight: '280px' }}
                    >
                      <track kind='captions' />
                    </video>
                    <Button
                      variant='destructive'
                      size='icon'
                      className='absolute top-2 right-2 size-7'
                      onClick={clearFile}
                    >
                      <X className='size-4' />
                    </Button>
                  </div>
                ) : preview ? (
                  <div className='relative'>
                    <img
                      src={preview}
                      alt='업로드된 이미지 미리보기'
                      className='w-full rounded-lg border object-contain'
                      style={{ maxHeight: '280px' }}
                    />
                    <Button
                      variant='destructive'
                      size='icon'
                      className='absolute top-2 right-2 size-7'
                      onClick={clearFile}
                    >
                      <X className='size-4' />
                    </Button>
                  </div>
                ) : (
                  <div
                    {...getRootProps()}
                    className={cn(
                      'flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-10 transition-colors',
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
                        JPG, PNG, WebP, BMP, MP4 형식 지원
                      </p>
                    </div>
                  </div>
                )}

                {/* Location input */}
                <div className='space-y-1.5'>
                  <label
                    htmlFor='location-input'
                    className='flex items-center gap-1.5 text-sm font-medium'
                  >
                    <MapPin className='size-3.5 text-muted-foreground' />
                    촬영 위치
                  </label>
                  <Input
                    id='location-input'
                    placeholder='예: 1층 로비'
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                  />
                  <p className='text-xs text-muted-foreground'>선택 사항</p>
                </div>

                {/* File info + analyze button */}
                {file && (
                  <div className='space-y-3'>
                    <div className='flex items-center gap-2 text-sm text-muted-foreground'>
                      {file && isVideoFile(file) ? (
                        <Video className='size-4 shrink-0' />
                      ) : (
                        <ImageIcon className='size-4 shrink-0' />
                      )}
                      <span className='truncate'>{file.name}</span>
                      <span className='shrink-0 text-xs'>
                        ({(file.size / 1024).toFixed(1)} KB)
                      </span>
                    </div>
                    <Button
                      className='w-full'
                      onClick={handleAnalyze}
                      disabled={isAnalyzing}
                    >
                      {isAnalyzing ? (
                        <>
                          <Loader2 className='size-4 animate-spin' />
                          분석 중...
                        </>
                      ) : (
                        '분석 시작'
                      )}
                    </Button>
                  </div>
                )}

                {/* Loading progress steps */}
                {isAnalyzing && <AnalysisProgress elapsed={elapsed} mediaType={file && isVideoFile(file) ? 'video' : 'image'} />}
              </CardContent>
            </Card>
          </div>

          {/* ── Right Panel: Results ── */}
          <div className='flex flex-col gap-4'>
            {!result && !isAnalyzing && (
              <Card>
                <CardContent className='flex flex-col items-center justify-center py-20 text-center'>
                  <div className='flex size-16 items-center justify-center rounded-2xl bg-muted'>
                    <Shield className='size-8 text-muted-foreground' />
                  </div>
                  <p className='mt-4 text-sm text-muted-foreground'>
                    이미지를 업로드하고 분석을 시작하면 결과가 여기에 표시됩니다
                  </p>
                </CardContent>
              </Card>
            )}

            {result && (
              <>
                {/* 3a. Preview Image */}
                {preview && (
                  <Card>
                    <CardContent className='flex items-center justify-center py-4'>
                      {result.media_type === 'video' ? (
                        <video
                          src={preview}
                          controls
                          className='max-h-48 rounded-lg border object-contain'
                        >
                          <track kind='captions' />
                        </video>
                      ) : (
                        <img
                          src={preview}
                          alt='분석된 이미지'
                          className='max-h-48 rounded-lg border object-contain'
                        />
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* 3b. Threat Level Banner */}
                <ThreatBanner result={result} />

                {/* 3b. Summary Card */}
                <SummaryCard result={result} />

                {/* 3c. QA Accordion */}
                <QAAccordion qaResults={result.qa_results} />

                {/* 3d. Security Report */}
                <SecurityReport report={result.report} />

                {/* 3e. Recommended Actions */}
                <RecommendedActions
                  actions={result.recommended_actions}
                  sopReference={result.sop_reference}
                />
              </>
            )}
          </div>
        </div>

        {/* ── History Table (full width below) ── */}
        <div className='mt-6'>
          <HistoryTable history={history} onRowClick={openDetail} />
        </div>

        <Dialog open={Boolean(detail)} onOpenChange={(open) => !open && setDetail(null)}>
          <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-4xl'>
            <DialogHeader>
              <DialogTitle>분석 이력 상세 보고서</DialogTitle>
            </DialogHeader>

            {detail && (
              <div className='space-y-4'>
                <Card>
                  <CardContent className='flex items-center justify-center py-4'>
                    {isVideoMedia(detail) ? (
                      <video
                        src={`/api/analysis/${detail.analysis_id}/media`}
                        controls
                        className='max-h-64 rounded-lg border object-contain'
                      >
                        <track kind='captions' />
                      </video>
                    ) : (
                      <img
                        src={`/api/analysis/${detail.analysis_id}/image`}
                        alt={detail.filename}
                        className='max-h-64 rounded-lg border object-contain'
                        onError={(e) => {
                          (e.target as HTMLImageElement).parentElement!.style.display = 'none'
                        }}
                      />
                    )}
                  </CardContent>
                </Card>
                <ThreatBanner result={detail} />
                <SummaryCard result={detail} />
                <QAAccordion qaResults={detail.qa_results} />
                <SecurityReport report={detail.report} />
                <RecommendedActions
                  actions={detail.recommended_actions}
                  sopReference={detail.sop_reference}
                />
              </div>
            )}
          </DialogContent>
        </Dialog>
      </Main>
    </>
  )
}
