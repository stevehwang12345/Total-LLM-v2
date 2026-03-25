import { useState, useEffect, useCallback, useRef } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  Bell,
  CheckCircle2,
  Loader2,
  Filter,
  AlertTriangle,
  ShieldAlert,
  Info,
  AlertOctagon,
} from 'lucide-react'
import { toast } from 'sonner'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

export const Route = createFileRoute('/_authenticated/alarms/')({
  component: AlarmsPage,
})

interface Alarm {
  id: string
  device_id: string
  severity: string
  description: string
  acknowledged: boolean
  created_at: string
  _isNew?: boolean
}

interface AlarmStats {
  total: number
  by_severity: Record<string, number>
  unacknowledged: number
}

const SEVERITY_MAP: Record<string, { label: string; color: string; barColor: string; icon: typeof AlertTriangle }> = {
  심각: { label: '심각', color: 'bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/20', barColor: '#ef4444', icon: AlertOctagon },
  높음: { label: '높음', color: 'bg-orange-500/15 text-orange-700 dark:text-orange-400 border-orange-500/20', barColor: '#f97316', icon: ShieldAlert },
  중간: { label: '중간', color: 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 border-yellow-500/20', barColor: '#eab308', icon: AlertTriangle },
  낮음: { label: '낮음', color: 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/20', barColor: '#22c55e', icon: Info },
  정보: { label: '정보', color: 'bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/20', barColor: '#3b82f6', icon: Info },
}

function AlarmsPage() {
  const [alarms, setAlarms] = useState<Alarm[]>([])
  const [stats, setStats] = useState<AlarmStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const fetchAlarms = useCallback(async () => {
    try {
      const res = await fetch('/api/alarms')
      if (res.ok) {
        const data = await res.json()
        setAlarms(Array.isArray(data) ? data : data.alarms || [])
      }
    } catch {
      void 0
    } finally {
      setIsLoading(false)
    }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch('/api/alarms/stats')
      if (res.ok) {
        setStats(await res.json())
      }
    } catch {
      void 0
    }
  }, [])

  useEffect(() => {
    fetchAlarms()
    fetchStats()
  }, [fetchAlarms, fetchStats])

  useEffect(() => {
    const es = new EventSource('/api/alarms/stream')
    eventSourceRef.current = es

    es.onmessage = (event) => {
      try {
        const newAlarm: Alarm = JSON.parse(event.data)
        newAlarm._isNew = true
        setAlarms((prev) => [newAlarm, ...prev])
        fetchStats()
        toast.info('새 알람', { description: newAlarm.description })

        setTimeout(() => {
          setAlarms((prev) =>
            prev.map((a) => (a.id === newAlarm.id ? { ...a, _isNew: false } : a))
          )
        }, 3000)
      } catch {
        void 0
      }
    }

    es.onerror = () => {
      es.close()
    }

    return () => {
      es.close()
    }
  }, [fetchStats])

  const handleAcknowledge = async (alarmId: string) => {
    setAcknowledgingId(alarmId)
    try {
      const res = await fetch(`/api/alarms/${alarmId}/acknowledge`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error('확인 처리 실패')
      setAlarms((prev) =>
        prev.map((a) => (a.id === alarmId ? { ...a, acknowledged: true } : a))
      )
      fetchStats()
      toast.success('알람 확인 완료')
    } catch {
      toast.error('알람 확인 실패')
    } finally {
      setAcknowledgingId(null)
    }
  }

  const filteredAlarms =
    filter === 'all' ? alarms : alarms.filter((a) => a.severity === filter)

  const chartData = stats?.by_severity
    ? Object.entries(stats.by_severity).map(([severity, count]) => ({
        severity,
        count,
        fill: SEVERITY_MAP[severity]?.barColor || '#6b7280',
      }))
    : []

  return (
    <>
      <Header fixed>
        <div className='flex w-full items-center justify-between'>
          <div className='flex items-center gap-2'>
            <Bell className='size-5 text-primary' />
            <h1 className='text-lg font-semibold'>알람 대시보드</h1>
            {stats && stats.unacknowledged > 0 && (
              <Badge variant='destructive'>{stats.unacknowledged} 미확인</Badge>
            )}
          </div>
          <div className='flex items-center gap-2'>
            <Filter className='size-4 text-muted-foreground' />
            <Select value={filter} onValueChange={setFilter}>
              <SelectTrigger className='w-28'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='all'>전체</SelectItem>
                <SelectItem value='심각'>심각</SelectItem>
                <SelectItem value='높음'>높음</SelectItem>
                <SelectItem value='중간'>중간</SelectItem>
                <SelectItem value='낮음'>낮음</SelectItem>
                <SelectItem value='정보'>정보</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </Header>
      <Main>
        <div className='mb-6 grid gap-6 lg:grid-cols-3'>
          <Card className='lg:col-span-1'>
            <CardHeader>
              <CardTitle className='text-base'>알람 통계</CardTitle>
            </CardHeader>
            <CardContent>
              {stats ? (
                <div className='space-y-4'>
                  <div className='grid grid-cols-2 gap-3'>
                    <div className='rounded-lg bg-muted/50 p-3 text-center'>
                      <p className='text-2xl font-bold'>{stats.total}</p>
                      <p className='text-xs text-muted-foreground'>전체</p>
                    </div>
                    <div className='rounded-lg bg-destructive/10 p-3 text-center'>
                      <p className='text-2xl font-bold text-destructive'>
                        {stats.unacknowledged}
                      </p>
                      <p className='text-xs text-muted-foreground'>미확인</p>
                    </div>
                  </div>
                  {chartData.length > 0 && (
                    <ResponsiveContainer width='100%' height={180}>
                      <BarChart data={chartData}>
                        <XAxis dataKey='severity' tick={{ fontSize: 12 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                        <Tooltip
                          contentStyle={{
                            borderRadius: '8px',
                            border: '1px solid var(--border)',
                            background: 'var(--card)',
                            color: 'var(--card-foreground)',
                          }}
                        />
                        <Bar dataKey='count' radius={[4, 4, 0, 0]}>
                          {chartData.map((entry) => (
                            <Cell key={entry.severity} fill={entry.fill} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              ) : (
                <div className='flex items-center justify-center py-10'>
                  <Loader2 className='size-6 animate-spin text-muted-foreground' />
                </div>
              )}
            </CardContent>
          </Card>

          <Card className='lg:col-span-2'>
            <CardHeader>
              <CardTitle className='text-base'>알람 목록</CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className='flex items-center justify-center py-10'>
                  <Loader2 className='size-6 animate-spin text-muted-foreground' />
                </div>
              ) : filteredAlarms.length === 0 ? (
                <p className='py-10 text-center text-sm text-muted-foreground'>
                  알람이 없습니다
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>시간</TableHead>
                      <TableHead>장비</TableHead>
                      <TableHead>심각도</TableHead>
                      <TableHead>내용</TableHead>
                      <TableHead className='text-right'>처리</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredAlarms.map((alarm) => {
                      const sevCfg = SEVERITY_MAP[alarm.severity] || SEVERITY_MAP['정보']
                      return (
                        <TableRow
                          key={alarm.id}
                          className={cn(
                            alarm._isNew &&
                              'animate-in fade-in slide-in-from-top-2 bg-primary/5'
                          )}
                        >
                          <TableCell className='text-xs'>
                            {new Date(alarm.created_at).toLocaleString('ko-KR')}
                          </TableCell>
                          <TableCell className='text-sm font-medium'>
                            {alarm.device_id}
                          </TableCell>
                          <TableCell>
                            <Badge variant='outline' className={sevCfg.color}>
                              {sevCfg.label}
                            </Badge>
                          </TableCell>
                          <TableCell className='max-w-xs truncate text-sm'>
                            {alarm.description}
                          </TableCell>
                          <TableCell className='text-right'>
                            {alarm.acknowledged ? (
                              <Badge variant='secondary' className='gap-1'>
                                <CheckCircle2 className='size-3' />
                                확인됨
                              </Badge>
                            ) : (
                              <Button
                                size='sm'
                                variant='outline'
                                onClick={() => handleAcknowledge(alarm.id)}
                                disabled={acknowledgingId === alarm.id}
                              >
                                {acknowledgingId === alarm.id ? (
                                  <Loader2 className='size-3 animate-spin' />
                                ) : (
                                  '확인'
                                )}
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
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
