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
  alarm_id: string
  device_id: string
  severity: string
  description: string
  acknowledged: boolean
  timestamp: string
  status?: string
  priority?: string
  analysis_id?: string
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

const STATUS_COLORS: Record<string, string> = {
  triggered: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400',
  acknowledged: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/20 dark:text-yellow-400',
  investigating: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',
  resolved: 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400',
  closed: 'bg-gray-100 text-gray-600 dark:bg-gray-500/20 dark:text-gray-400',
  false_alarm: 'bg-gray-100 text-gray-500 dark:bg-gray-500/20 dark:text-gray-500',
}

const PRIORITY_COLORS: Record<string, string> = {
  P1: 'bg-red-500 text-white',
  P2: 'bg-orange-400 text-white',
  P3: 'bg-yellow-400 text-gray-900',
  P4: 'bg-green-400 text-white',
}

const STATUS_LABELS: Record<string, string> = {
  triggered: '발생',
  acknowledged: '확인',
  investigating: '조사중',
  resolved: '해결',
  closed: '종결',
  false_alarm: '오경보',
}

const VALID_TRANSITIONS: Record<string, string[]> = {
  triggered: ['acknowledged', 'false_alarm'],
  acknowledged: ['investigating', 'resolved', 'false_alarm'],
  investigating: ['resolved', 'false_alarm'],
  resolved: ['closed'],
  closed: [],
  false_alarm: ['closed'],
}

function AlarmsPage() {
  const [alarms, setAlarms] = useState<Alarm[]>([])
  const [stats, setStats] = useState<AlarmStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [priorityFilter, setPriorityFilter] = useState<string>('all')
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null)
  const [transitioningId, setTransitioningId] = useState<string | null>(null)
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
             prev.map((a) => (a.alarm_id === newAlarm.alarm_id ? { ...a, _isNew: false } : a))
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
         prev.map((a) => (a.alarm_id === alarmId ? { ...a, acknowledged: true } : a))
       )
       fetchStats()
       toast.success('알람 확인 완료')
     } catch {
       toast.error('알람 확인 실패')
     } finally {
       setAcknowledgingId(null)
     }
   }

  const handleTransition = async (alarmId: string, newStatus: string) => {
    setTransitioningId(alarmId)
    try {
      const res = await fetch(`/api/alarms/${alarmId}/transition`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
      if (!res.ok) throw new Error('상태 전이 실패')
      setAlarms((prev) =>
        prev.map((a) =>
          a.alarm_id === alarmId
            ? { ...a, status: newStatus, acknowledged: newStatus !== 'triggered' ? true : a.acknowledged }
            : a
        )
      )
      fetchStats()
      toast.success(`알람 상태 변경: ${STATUS_LABELS[newStatus] || newStatus}`)
    } catch {
      toast.error('알람 상태 전이 실패')
    } finally {
      setTransitioningId(null)
    }
  }

  const filteredAlarms = alarms.filter((a) => {
    if (filter !== 'all' && a.severity !== filter) return false
    if (statusFilter !== 'all' && (a.status || 'triggered') !== statusFilter) return false
    if (priorityFilter !== 'all' && a.priority !== priorityFilter) return false
    return true
  })

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
                <SelectValue placeholder='심각도' />
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
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className='w-28'>
                <SelectValue placeholder='상태' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='all'>전체 상태</SelectItem>
                {Object.entries(STATUS_LABELS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={priorityFilter} onValueChange={setPriorityFilter}>
              <SelectTrigger className='w-24'>
                <SelectValue placeholder='우선순위' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='all'>전체</SelectItem>
                <SelectItem value='P1'>P1</SelectItem>
                <SelectItem value='P2'>P2</SelectItem>
                <SelectItem value='P3'>P3</SelectItem>
                <SelectItem value='P4'>P4</SelectItem>
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
                      <TableHead>상태</TableHead>
                      <TableHead>우선순위</TableHead>
                      <TableHead>내용</TableHead>
                      <TableHead className='text-right'>처리</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                     {filteredAlarms.map((alarm) => {
                       const sevCfg = SEVERITY_MAP[alarm.severity] || SEVERITY_MAP['정보']
                       const alarmStatus = alarm.status || 'triggered'
                       const nextStatuses = VALID_TRANSITIONS[alarmStatus] || []
                       return (
                         <TableRow
                           key={alarm.alarm_id}
                           className={cn(
                             alarm._isNew &&
                               'animate-in fade-in slide-in-from-top-2 bg-primary/5'
                           )}
                         >
                          <TableCell className='text-xs'>
                            {new Date(alarm.timestamp).toLocaleString('ko-KR')}
                          </TableCell>
                          <TableCell className='text-sm font-medium'>
                            {alarm.device_id}
                          </TableCell>
                          <TableCell>
                            <Badge variant='outline' className={sevCfg.color}>
                              {sevCfg.label}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant='outline'
                              className={cn('text-xs', STATUS_COLORS[alarmStatus])}
                            >
                              {STATUS_LABELS[alarmStatus] || alarmStatus}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {alarm.priority ? (
                              <Badge className={cn('text-xs font-semibold', PRIORITY_COLORS[alarm.priority])}>
                                {alarm.priority}
                              </Badge>
                            ) : (
                              <span className='text-xs text-muted-foreground'>—</span>
                            )}
                          </TableCell>
                          <TableCell className='max-w-xs truncate text-sm'>
                            {alarm.description}
                          </TableCell>
                           <TableCell className='text-right'>
                             <div className='flex items-center justify-end gap-1'>
                               {!alarm.acknowledged && alarmStatus === 'triggered' && (
                                 <Button
                                   size='sm'
                                   variant='outline'
                                   onClick={() => handleAcknowledge(alarm.alarm_id)}
                                   disabled={acknowledgingId === alarm.alarm_id}
                                 >
                                   {acknowledgingId === alarm.alarm_id ? (
                                     <Loader2 className='size-3 animate-spin' />
                                   ) : (
                                     '확인'
                                   )}
                                 </Button>
                               )}
                               {nextStatuses.map((next) => (
                                 <Button
                                   key={next}
                                   size='sm'
                                   variant='ghost'
                                   className='h-7 px-2 text-xs'
                                   onClick={() => handleTransition(alarm.alarm_id, next)}
                                   disabled={transitioningId === alarm.alarm_id}
                                 >
                                   {transitioningId === alarm.alarm_id ? (
                                     <Loader2 className='size-3 animate-spin' />
                                   ) : (
                                     STATUS_LABELS[next] || next
                                   )}
                                 </Button>
                               ))}
                               {alarmStatus === 'closed' && (
                                 <Badge variant='secondary' className='gap-1'>
                                   <CheckCircle2 className='size-3' />
                                   종결
                                 </Badge>
                               )}
                             </div>
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
