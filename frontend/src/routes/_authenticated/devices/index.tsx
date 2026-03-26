import { useState, useEffect, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  Monitor,
  Plus,
  Cctv,
  DoorOpen,
  Wifi,
  WifiOff,
  AlertCircle,
  MapPin,
  Loader2,
  Activity,
  Clock,
  Pencil,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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
import { cn } from '@/lib/utils'
import { ConfirmDialog } from '@/components/confirm-dialog'

export const Route = createFileRoute('/_authenticated/devices/')({
  component: DevicesPage,
})

interface Device {
  device_id: string
  device_type: string
  manufacturer?: string
  ip_address: string
  port?: number
  protocol?: string
  location: string
  status: string
  last_seen?: string
  firmware_version?: string
  security_grade?: string
  last_health_check?: string
}

interface HealthResult {
  status: string
  latency_ms: number | null
  checked_at: string
}

interface DeviceStats {
  total: number
  online: number
  offline: number
  error: number
}

const STATUS_CONFIG: Record<string, { label: string; className: string; icon: typeof Wifi }> = {
  online: { label: '온라인', className: 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/20', icon: Wifi },
  offline: { label: '오프라인', className: 'bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/20', icon: WifiOff },
  error: { label: '오류', className: 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 border-yellow-500/20', icon: AlertCircle },
}

function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editingDevice, setEditingDevice] = useState<Device | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Device | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [healthResults, setHealthResults] = useState<Record<string, HealthResult>>({})
  const [checkingHealthId, setCheckingHealthId] = useState<string | null>(null)
  const [deviceStats, setDeviceStats] = useState<DeviceStats | null>(null)

  const [formDeviceId, setFormDeviceId] = useState('')
  const [formType, setFormType] = useState('CCTV')
  const [formIp, setFormIp] = useState('')
  const [formLocation, setFormLocation] = useState('')
  const [formManufacturer, setFormManufacturer] = useState('Unknown')
  const [formPort, setFormPort] = useState('554')
  const [formProtocol, setFormProtocol] = useState('RTSP')

  const [editType, setEditType] = useState('CCTV')
  const [editIp, setEditIp] = useState('')
  const [editLocation, setEditLocation] = useState('')
  const [editStatus, setEditStatus] = useState('online')

  const fetchDevices = useCallback(async () => {
    try {
      const res = await fetch('/api/devices', { cache: 'no-store' })
      if (res.ok) {
        const data = await res.json()
        setDevices(Array.isArray(data) ? data : data.devices || [])
      }
    } catch {
      toast.error('장비 목록 조회 실패')
    } finally {
      setIsLoading(false)
    }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch('/api/devices/stats', { cache: 'no-store' })
      if (res.ok) {
        setDeviceStats(await res.json())
      }
    } catch {
      void 0
    }
  }, [])

  useEffect(() => {
    fetchDevices()
    fetchStats()
  }, [fetchDevices, fetchStats])

  useEffect(() => {
    const handleDevicesChanged = () => {
      void fetchDevices()
      void fetchStats()
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void fetchDevices()
        void fetchStats()
      }
    }

    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        void fetchDevices()
        void fetchStats()
      }
    }, 15000)

    window.addEventListener('devices:changed', handleDevicesChanged)
    window.addEventListener('focus', handleDevicesChanged)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      window.clearInterval(interval)
      window.removeEventListener('devices:changed', handleDevicesChanged)
      window.removeEventListener('focus', handleDevicesChanged)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [fetchDevices, fetchStats])

  const handleHealthCheck = async (deviceId: string) => {
    setCheckingHealthId(deviceId)
    try {
      const res = await fetch(`/api/devices/${deviceId}/health`)
      if (!res.ok) throw new Error('헬스체크 실패')
      const data = await res.json()
      setHealthResults((prev) => ({
        ...prev,
        [deviceId]: {
          status: data.status,
          latency_ms: data.latency_ms ?? null,
          checked_at: new Date().toISOString(),
        },
      }))
      toast.success('헬스체크 완료', {
        description: `${deviceId}: ${data.status}${data.latency_ms != null ? ` (${data.latency_ms}ms)` : ''}`,
      })
    } catch {
      toast.error('헬스체크 실패', { description: deviceId })
    } finally {
      setCheckingHealthId(null)
    }
  }

  const handleRegister = async () => {
    if (!formDeviceId || !formIp || !formLocation) {
      toast.error('모든 필드를 입력해주세요')
      return
    }
    setIsSubmitting(true)
    try {
      const res = await fetch('/api/devices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: formDeviceId,
          device_type: formType,
          manufacturer: formManufacturer || 'Unknown',
          ip_address: formIp,
          port: Number(formPort) || 554,
          protocol: formProtocol || 'RTSP',
          location: formLocation,
          status: 'online',
        }),
      })
      if (!res.ok) throw new Error(`등록 실패: ${res.status}`)
      toast.success('장비 등록 완료', { description: `${formDeviceId} 등록됨` })
      setDialogOpen(false)
      setFormDeviceId('')
      setFormIp('')
      setFormLocation('')
      setFormManufacturer('Unknown')
      setFormPort('554')
      setFormProtocol('RTSP')
      fetchDevices()
    } catch (err) {
      const message = err instanceof Error ? err.message : '등록 중 오류 발생'
      toast.error('장비 등록 실패', { description: message })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleOpenEdit = (device: Device) => {
    setEditingDevice(device)
    setEditType(device.device_type)
    setEditIp(device.ip_address)
    setEditLocation(device.location)
    setEditStatus(device.status)
    setEditDialogOpen(true)
  }

  const handleUpdateDevice = async () => {
    if (!editingDevice) return
    try {
      const res = await fetch(`/api/devices/${editingDevice.device_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_type: editType,
          ip_address: editIp,
          location: editLocation,
          status: editStatus,
        }),
      })
      if (!res.ok) throw new Error(`수정 실패: ${res.status}`)
      toast.success('장비 정보 수정 완료')
      setEditDialogOpen(false)
      setEditingDevice(null)
      await fetchDevices()
      await fetchStats()
    } catch (err) {
      const message = err instanceof Error ? err.message : '수정 중 오류'
      toast.error('장비 수정 실패', { description: message })
    }
  }

  const handleDeleteDevice = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      const res = await fetch(`/api/devices/${deleteTarget.device_id}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error(`삭제 실패: ${res.status}`)
      toast.success('장비 삭제 완료', { description: deleteTarget.device_id })
      setDeleteTarget(null)
      await fetchDevices()
      await fetchStats()
    } catch (err) {
      const message = err instanceof Error ? err.message : '삭제 중 오류'
      toast.error('장비 삭제 실패', { description: message })
    } finally {
      setIsDeleting(false)
    }
  }

  const DeviceIcon = ({ type }: { type: string }) => {
    if (type === 'CCTV' || type === 'cctv') return <Cctv className='size-5' />
    if (type === 'ACU' || type === 'acu') return <DoorOpen className='size-5' />
    return <Monitor className='size-5' />
  }

  const getRegistrationBadge = (location: string) => {
    if (location === 'Auto-Discovered') {
      return { variant: 'default' as const, label: '자동' }
    }
    if (location.includes('Manual') || location === 'Manual') {
      return { variant: 'destructive' as const, label: '수동 확인' }
    }
    return { variant: 'secondary' as const, label: '기존' }
  }

  const statusSummary = deviceStats ?? {
    total: devices.length,
    online: devices.filter((d) => d.status === 'online').length,
    offline: devices.filter((d) => d.status === 'offline').length,
    error: devices.filter((d) => d.status === 'error').length,
  }

  return (
    <>
      <Header fixed>
        <div className='flex w-full items-center justify-between'>
          <div className='flex items-center gap-2'>
            <Monitor className='size-5 text-primary' />
            <h1 className='text-lg font-semibold'>장비 관리</h1>
            <Badge variant='secondary'>{devices.length}대</Badge>
          </div>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size='sm'>
                <Plus className='size-4' />
                장비 등록
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>새 장비 등록</DialogTitle>
                <DialogDescription>
                  보안 시스템에 새로운 장비를 등록합니다
                </DialogDescription>
              </DialogHeader>
              <div className='grid gap-4 py-4'>
                <div className='grid gap-2'>
                  <Label htmlFor='device-id'>장비 ID</Label>
                  <Input
                    id='device-id'
                    placeholder='예: CAM-001'
                    value={formDeviceId}
                    onChange={(e) => setFormDeviceId(e.target.value)}
                  />
                </div>
                <div className='grid gap-2'>
                  <Label>장비 유형</Label>
                  <Select value={formType} onValueChange={setFormType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value='CCTV'>CCTV</SelectItem>
                      <SelectItem value='ACU'>출입통제장치 (ACU)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className='grid gap-2'>
                  <Label htmlFor='ip-addr'>IP 주소</Label>
                  <Input
                    id='ip-addr'
                    placeholder='예: 192.168.1.100'
                    value={formIp}
                    onChange={(e) => setFormIp(e.target.value)}
                  />
                </div>
                <div className='grid gap-2'>
                  <Label htmlFor='manufacturer'>제조사</Label>
                  <Input
                    id='manufacturer'
                    placeholder='예: Hanwha Vision'
                    value={formManufacturer}
                    onChange={(e) => setFormManufacturer(e.target.value)}
                  />
                </div>
                <div className='grid grid-cols-2 gap-3'>
                  <div className='grid gap-2'>
                    <Label htmlFor='device-port'>포트</Label>
                    <Input
                      id='device-port'
                      placeholder='554'
                      value={formPort}
                      onChange={(e) => setFormPort(e.target.value)}
                    />
                  </div>
                  <div className='grid gap-2'>
                    <Label htmlFor='device-protocol'>프로토콜</Label>
                    <Input
                      id='device-protocol'
                      placeholder='RTSP'
                      value={formProtocol}
                      onChange={(e) => setFormProtocol(e.target.value)}
                    />
                  </div>
                </div>
                <div className='grid gap-2'>
                  <Label htmlFor='location'>설치 위치</Label>
                  <Input
                    id='location'
                    placeholder='예: 1층 정문'
                    value={formLocation}
                    onChange={(e) => setFormLocation(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant='outline'
                  onClick={() => setDialogOpen(false)}
                >
                  취소
                </Button>
                <Button onClick={handleRegister} disabled={isSubmitting}>
                  {isSubmitting ? (
                    <>
                      <Loader2 className='size-4 animate-spin' />
                      등록 중...
                    </>
                  ) : (
                    '등록'
                  )}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </Header>
      <Main>
        <div className='mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4'>
          <Card className='py-4'>
            <CardContent className='flex items-center gap-3 px-4'>
              <div className='flex size-10 items-center justify-center rounded-lg bg-primary/10'>
                <Monitor className='size-5 text-primary' />
              </div>
              <div>
                <p className='text-2xl font-bold'>{statusSummary.total}</p>
                <p className='text-xs text-muted-foreground'>전체 장비</p>
              </div>
            </CardContent>
          </Card>
          <Card className='py-4'>
            <CardContent className='flex items-center gap-3 px-4'>
              <div className='flex size-10 items-center justify-center rounded-lg bg-green-500/10'>
                <Wifi className='size-5 text-green-600' />
              </div>
              <div>
                <p className='text-2xl font-bold'>{statusSummary.online}</p>
                <p className='text-xs text-muted-foreground'>온라인</p>
              </div>
            </CardContent>
          </Card>
          <Card className='py-4'>
            <CardContent className='flex items-center gap-3 px-4'>
              <div className='flex size-10 items-center justify-center rounded-lg bg-red-500/10'>
                <WifiOff className='size-5 text-red-600' />
              </div>
              <div>
                <p className='text-2xl font-bold'>{statusSummary.offline}</p>
                <p className='text-xs text-muted-foreground'>오프라인</p>
              </div>
            </CardContent>
          </Card>
          <Card className='py-4'>
            <CardContent className='flex items-center gap-3 px-4'>
              <div className='flex size-10 items-center justify-center rounded-lg bg-yellow-500/10'>
                <AlertCircle className='size-5 text-yellow-600' />
              </div>
              <div>
                <p className='text-2xl font-bold'>{statusSummary.error}</p>
                <p className='text-xs text-muted-foreground'>오류</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {isLoading ? (
          <div className='flex items-center justify-center py-20'>
            <Loader2 className='size-8 animate-spin text-muted-foreground' />
          </div>
        ) : devices.length === 0 ? (
          <div className='flex flex-col items-center justify-center gap-3 py-20'>
            <Monitor className='size-12 text-muted-foreground/50' />
            <p className='text-muted-foreground'>등록된 장비가 없습니다</p>
            <Button size='sm' onClick={() => setDialogOpen(true)}>
              <Plus className='size-4' />
              장비 등록
            </Button>
          </div>
        ) : (
          <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
            {devices.map((device) => {
              const statusCfg = STATUS_CONFIG[device.status] || STATUS_CONFIG.offline
              const StatusIcon = statusCfg.icon
              return (
                <Card
                   key={device.device_id}
                   className={cn(
                     'cursor-pointer transition-shadow hover:shadow-md',
                     selectedDevice?.device_id === device.device_id && 'ring-2 ring-primary'
                   )}
                   onClick={() =>
                     setSelectedDevice(
                       selectedDevice?.device_id === device.device_id ? null : device
                     )
                   }
                 >
                   <CardHeader className='pb-3'>
                     <div className='flex items-center justify-between'>
                       <div className='flex items-center gap-2'>
                         <DeviceIcon type={device.device_type} />
                         <CardTitle className='text-base'>
                           {device.device_id}
                         </CardTitle>
                       </div>
                       <Badge variant='outline' className={statusCfg.className}>
                         <StatusIcon className='mr-1 size-3' />
                         {statusCfg.label}
                       </Badge>
                     </div>
                   </CardHeader>
                   <CardContent className='space-y-2'>
                     <div className='flex items-center gap-2 text-sm text-muted-foreground'>
                       <Badge variant='secondary' className='text-xs'>
                         {device.device_type}
                       </Badge>
                       {device.security_grade && (
                         <Badge variant='outline' className='text-xs'>
                           등급 {device.security_grade}
                         </Badge>
                       )}
                     </div>
                    <div className='flex items-center gap-1.5 text-sm text-muted-foreground'>
                      <Wifi className='size-3.5' />
                      {device.ip_address}
                    </div>
                     <div className='flex items-center gap-2 text-sm text-muted-foreground'>
                       <div className='flex items-center gap-1.5'>
                         <MapPin className='size-3.5' />
                         {device.location}
                       </div>
                       <Badge variant={getRegistrationBadge(device.location).variant} className='text-xs'>
                         {getRegistrationBadge(device.location).label}
                       </Badge>
                     </div>
                    {device.last_health_check && (
                      <div className='flex items-center gap-1.5 text-xs text-muted-foreground'>
                        <Clock className='size-3' />
                        헬스체크: {new Date(device.last_health_check).toLocaleString('ko-KR')}
                      </div>
                    )}
                     <div className='flex items-center gap-2 pt-1'>
                       <Button
                         size='sm'
                        variant='outline'
                        className='h-7 gap-1 px-2 text-xs'
                        onClick={(e) => {
                          e.stopPropagation()
                          handleHealthCheck(device.device_id)
                        }}
                        disabled={checkingHealthId === device.device_id}
                      >
                        {checkingHealthId === device.device_id ? (
                          <Loader2 className='size-3 animate-spin' />
                        ) : (
                          <Activity className='size-3' />
                        )}
                         헬스체크
                       </Button>
                       <Button
                         size='sm'
                         variant='outline'
                         className='h-7 gap-1 px-2 text-xs'
                         onClick={(e) => {
                           e.stopPropagation()
                           handleOpenEdit(device)
                         }}
                       >
                         <Pencil className='size-3' />
                         수정
                       </Button>
                       <Button
                         size='sm'
                         variant='outline'
                         className='h-7 gap-1 px-2 text-xs text-destructive hover:text-destructive'
                         onClick={(e) => {
                           e.stopPropagation()
                           setDeleteTarget(device)
                         }}
                       >
                         <Trash2 className='size-3' />
                         삭제
                       </Button>
                     </div>
                    {healthResults[device.device_id] && (
                      <div className={cn(
                        'rounded-md p-2 text-xs',
                        healthResults[device.device_id].status === 'healthy'
                          ? 'bg-green-500/10 text-green-700 dark:text-green-400'
                          : 'bg-red-500/10 text-red-700 dark:text-red-400'
                      )}>
                        <div className='flex items-center justify-between'>
                          <span className='font-medium'>
                            {healthResults[device.device_id].status === 'healthy' ? '정상' : '이상'}
                          </span>
                          {healthResults[device.device_id].latency_ms != null && (
                            <span>{healthResults[device.device_id].latency_ms}ms</span>
                          )}
                        </div>
                        <p className='mt-0.5 text-muted-foreground'>
                          {new Date(healthResults[device.device_id].checked_at).toLocaleString('ko-KR')}
                        </p>
                      </div>
                    )}
                    {selectedDevice?.device_id === device.device_id && device.last_seen && (
                      <div className='mt-2 rounded-md bg-muted/50 p-2 text-xs text-muted-foreground'>
                        마지막 연결: {new Date(device.last_seen).toLocaleString('ko-KR')}
                      </div>
                    )}
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}

        <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>장비 정보 수정</DialogTitle>
              <DialogDescription>
                {editingDevice?.device_id} 설정을 업데이트합니다
              </DialogDescription>
            </DialogHeader>
            <div className='grid gap-4 py-4'>
              <div className='grid gap-2'>
                <Label>장비 유형</Label>
                <Select value={editType} onValueChange={setEditType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='CCTV'>CCTV</SelectItem>
                    <SelectItem value='ACU'>ACU</SelectItem>
                    <SelectItem value='Unknown'>Unknown</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className='grid gap-2'>
                <Label htmlFor='edit-ip'>IP 주소</Label>
                <Input id='edit-ip' value={editIp} onChange={(e) => setEditIp(e.target.value)} />
              </div>
              <div className='grid gap-2'>
                <Label htmlFor='edit-location'>위치</Label>
                <Input id='edit-location' value={editLocation} onChange={(e) => setEditLocation(e.target.value)} />
              </div>
              <div className='grid gap-2'>
                <Label>상태</Label>
                <Select value={editStatus} onValueChange={setEditStatus}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='online'>online</SelectItem>
                    <SelectItem value='offline'>offline</SelectItem>
                    <SelectItem value='maintenance'>maintenance</SelectItem>
                    <SelectItem value='error'>error</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant='outline' onClick={() => setEditDialogOpen(false)}>취소</Button>
              <Button onClick={handleUpdateDevice}>저장</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <ConfirmDialog
          open={!!deleteTarget}
          onOpenChange={(open) => !open && setDeleteTarget(null)}
          title='장비 삭제'
          desc={`"${deleteTarget?.device_id}" 장비를 삭제하시겠습니까?`}
          confirmText='삭제'
          cancelBtnText='취소'
          destructive
          isLoading={isDeleting}
          handleConfirm={handleDeleteDevice}
        />
      </Main>
    </>
  )
}
