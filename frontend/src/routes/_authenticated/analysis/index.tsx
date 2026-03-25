import { useState, useEffect, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useDropzone } from 'react-dropzone'
import {
  Camera,
  Upload,
  Loader2,
  Image as ImageIcon,
  AlertTriangle,
  X,
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
import { cn } from '@/lib/utils'

export const Route = createFileRoute('/_authenticated/analysis/')({
  component: AnalysisPage,
})

interface AnalysisResult {
  id: string
  incident_type: string
  severity: string
  confidence: number
  description: string
  qa_results?: Array<{ question: string; answer: string }>
  created_at: string
  filename?: string
}

const SEVERITY_CONFIG: Record<string, { label: string; className: string }> = {
  심각: { label: '심각', className: 'bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/20' },
  높음: { label: '높음', className: 'bg-orange-500/15 text-orange-700 dark:text-orange-400 border-orange-500/20' },
  중간: { label: '중간', className: 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 border-yellow-500/20' },
  낮음: { label: '낮음', className: 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/20' },
  정보: { label: '정보', className: 'bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/20' },
}

function SeverityBadge({ severity }: { severity: string }) {
  const config = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG['정보']
  return (
    <Badge variant='outline' className={config.className}>
      {config.label}
    </Badge>
  )
}

function AnalysisPage() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [history, setHistory] = useState<AnalysisResult[]>([])

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/analysis')
      if (res.ok) {
        const data = await res.json()
        setHistory(Array.isArray(data) ? data : data.analyses || [])
      }
    } catch {
      void 0
    }
  }, [])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

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
    accept: { 'image/*': ['.jpg', '.jpeg', '.png', '.bmp', '.webp'] },
    maxFiles: 1,
    multiple: false,
  })

  const handleAnalyze = async () => {
    if (!file) return
    setIsAnalyzing(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/analysis/upload', {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error(`분석 실패: ${res.status}`)
      const data = await res.json()
      setResult(data)
      toast.success('분석 완료', { description: `사건 유형: ${data.incident_type}` })
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
  }

  return (
    <>
      <Header fixed>
        <div className='flex items-center gap-2'>
          <Camera className='size-5 text-primary' />
          <h1 className='text-lg font-semibold'>CCTV 영상 분석</h1>
        </div>
      </Header>
      <Main>
        <div className='grid gap-6 lg:grid-cols-2'>
          <div className='flex flex-col gap-6'>
            <Card>
              <CardHeader>
                <CardTitle>이미지 업로드</CardTitle>
                <CardDescription>
                  분석할 CCTV 캡처 이미지를 업로드하세요
                </CardDescription>
              </CardHeader>
              <CardContent>
                {!preview ? (
                  <div
                    {...getRootProps()}
                    className={cn(
                      'flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-12 transition-colors',
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
                        JPG, PNG, WebP 형식 지원
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className='relative'>
                    <img
                      src={preview}
                      alt='업로드된 이미지 미리보기'
                      className='w-full rounded-lg border object-contain'
                      style={{ maxHeight: '300px' }}
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
                )}
                {file && (
                  <div className='mt-4 flex items-center justify-between'>
                    <div className='flex items-center gap-2 text-sm text-muted-foreground'>
                      <ImageIcon className='size-4' />
                      {file.name}
                      <span className='text-xs'>
                        ({(file.size / 1024).toFixed(1)} KB)
                      </span>
                    </div>
                    <Button
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
              </CardContent>
            </Card>

            {result && (
              <Card>
                <CardHeader>
                  <div className='flex items-center justify-between'>
                    <CardTitle>분석 결과</CardTitle>
                    <SeverityBadge severity={result.severity} />
                  </div>
                </CardHeader>
                <CardContent className='space-y-4'>
                  <div className='grid grid-cols-2 gap-4'>
                    <div>
                      <p className='text-xs text-muted-foreground'>사건 유형</p>
                      <p className='text-sm font-medium'>{result.incident_type}</p>
                    </div>
                    <div>
                      <p className='text-xs text-muted-foreground'>신뢰도</p>
                      <p className='text-sm font-medium'>
                        {(result.confidence * 100).toFixed(1)}%
                      </p>
                    </div>
                  </div>
                  {result.description && (
                    <div>
                      <p className='text-xs text-muted-foreground'>설명</p>
                      <p className='mt-1 text-sm'>{result.description}</p>
                    </div>
                  )}
                  {result.qa_results && result.qa_results.length > 0 && (
                    <div>
                      <p className='mb-2 text-xs text-muted-foreground'>
                        질의응답 결과
                      </p>
                      <div className='space-y-2'>
                        {result.qa_results.map((qa) => (
                          <div
                            key={`qa-${result.id}-${qa.question}`}
                            className='rounded-md bg-muted/50 p-3'
                          >
                            <p className='text-xs font-medium'>Q: {qa.question}</p>
                            <p className='mt-1 text-xs text-muted-foreground'>
                              A: {qa.answer}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

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
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>일시</TableHead>
                      <TableHead>사건 유형</TableHead>
                      <TableHead>심각도</TableHead>
                      <TableHead>신뢰도</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {history.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell className='text-xs'>
                          {new Date(item.created_at).toLocaleString('ko-KR')}
                        </TableCell>
                        <TableCell className='text-sm'>
                          {item.incident_type}
                        </TableCell>
                        <TableCell>
                          <SeverityBadge severity={item.severity} />
                        </TableCell>
                        <TableCell className='text-sm'>
                          {(item.confidence * 100).toFixed(1)}%
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      </Main>
    </>
  )
}
