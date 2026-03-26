import { useCallback, useEffect, useMemo, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  AlertTriangle,
  Loader2,
  Radar,
  RefreshCcw,
  Search,
  Plus,
  Sparkles,
} from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'

export const Route = createFileRoute('/_authenticated/discovery/')({
  component: DiscoveryPage,
})

interface ScanItem {
  scan_id: string
  cidr: string
  status: string
  started_at?: string
  completed_at?: string | null
  total_found?: number
}

interface DiscoveredDevice {
  id: number
  ip_address: string
  mac_address?: string | null
  hostname?: string | null
  vendor?: string | null
  open_ports?: number[]
  http_banner?: Record<string, unknown> | null
  onvif_info?: Record<string, unknown> | null
  mdns_info?: Record<string, unknown> | null
  llm_profile?: {
    device_type?: string
    manufacturer?: string
    model_name?: string
    protocol?: string
    confidence?: number
    reasoning?: string
    suggested_device_id?: string
    consistency_result?: {
      consistent: boolean
      score: number
      mismatches?: Array<{
        field: string
        expected: string
        actual: string
        evidence: string
        severity: string
      }>
      checked_at?: string
    }
  } | null
  status: string
  device_id?: string | null
}

function DiscoveryPage() {
  const [cidr, setCidr] = useState('192.168.1.0/24')
  const [isStarting, setIsStarting] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [scans, setScans] = useState<ScanItem[]>([])
  const [selectedScanId, setSelectedScanId] = useState<string | null>(null)
  const [devices, setDevices] = useState<DiscoveredDevice[]>([])
  const [activeActionId, setActiveActionId] = useState<number | null>(null)
  const [manualDialog, setManualDialog] = useState<{
    open: boolean
    deviceId: number | null
    deviceType: string
    manufacturer: string
    protocol: string
    port: string
    location: string
    mismatches: Array<{ field: string; evidence: string }>
  }>({
    open: false,
    deviceId: null,
    deviceType: '',
    manufacturer: '',
    protocol: '',
    port: '554',
    location: 'Auto-Discovered',
    mismatches: [],
  })

  const selectedScan = useMemo(
    () => scans.find((item) => item.scan_id === selectedScanId) ?? null,
    [scans, selectedScanId]
  )

  const hasRunningScan = useMemo(
    () => scans.some((item) => item.status === 'running' || item.status === 'queued'),
    [scans]
  )

  const fetchScans = useCallback(async () => {
    const res = await fetch('/api/discovery/scans?limit=20', { cache: 'no-store' })
    if (!res.ok) throw new Error(`스캔 목록 조회 실패: ${res.status}`)
    const payload = await res.json()
    const items = Array.isArray(payload.items) ? payload.items : []
    setScans(items)
    if (!selectedScanId && items.length > 0) {
      setSelectedScanId(items[0].scan_id)
    }
  }, [selectedScanId])

  const fetchResults = useCallback(async (scanId: string) => {
    const res = await fetch(`/api/discovery/scans/${scanId}/results`, { cache: 'no-store' })
    if (!res.ok) throw new Error(`스캔 결과 조회 실패: ${res.status}`)
    const payload = await res.json()
    setDevices(Array.isArray(payload.devices) ? payload.devices : [])
  }, [])

  useEffect(() => {
    const run = async () => {
      try {
        await fetchScans()
      } catch {
        toast.error('디스커버리 스캔 목록을 불러오지 못했습니다')
      }
    }
    void run()
  }, [fetchScans])

  useEffect(() => {
    if (!selectedScanId) {
      setDevices([])
      return
    }
    const run = async () => {
      try {
        await fetchResults(selectedScanId)
      } catch {
        toast.error('스캔 결과를 불러오지 못했습니다')
      }
    }
    void run()
  }, [selectedScanId, fetchResults])

  useEffect(() => {
    if (!hasRunningScan) return

    const interval = window.setInterval(() => {
      void fetchScans()
      if (selectedScanId) {
        void fetchResults(selectedScanId)
      }
    }, 3000)

    return () => window.clearInterval(interval)
  }, [hasRunningScan, fetchScans, fetchResults, selectedScanId])

  const handleStartScan = async () => {
    if (!cidr.trim()) {
      toast.error('CIDR을 입력해주세요')
      return
    }
    setIsStarting(true)
    try {
      const res = await fetch('/api/discovery/scans', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cidr: cidr.trim(), timeout_sec: 90 }),
      })
      if (!res.ok) throw new Error(`스캔 시작 실패: ${res.status}`)
      const payload = await res.json()
      toast.success('스캔이 시작되었습니다', { description: payload.scan_id })
      setSelectedScanId(payload.scan_id)
      await fetchScans()
    } catch (err) {
      const msg = err instanceof Error ? err.message : '스캔 시작 중 오류'
      toast.error('스캔 시작 실패', { description: msg })
    } finally {
      setIsStarting(false)
    }
  }

  const handleRefresh = async () => {
    setIsRefreshing(true)
    try {
      await fetchScans()
      if (selectedScanId) {
        await fetchResults(selectedScanId)
      }
    } catch {
      toast.error('새로고침 실패')
    } finally {
      setIsRefreshing(false)
    }
  }

  const handleProfile = async (deviceId: number) => {
    if (!selectedScanId) return
    setActiveActionId(deviceId)
    try {
      const res = await fetch(`/api/discovery/scans/${selectedScanId}/devices/${deviceId}/profile`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error(`프로파일링 실패: ${res.status}`)
      toast.success('LLM 프로파일링 완료')
      await fetchResults(selectedScanId)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '프로파일링 오류'
      toast.error('프로파일링 실패', { description: msg })
    } finally {
      setActiveActionId(null)
    }
  }

  const doRegister = async (deviceId: number, payload: Record<string, unknown>) => {
    if (!selectedScanId) return
    setActiveActionId(deviceId)
    try {
      const res = await fetch(`/api/discovery/scans/${selectedScanId}/devices/${deviceId}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(`등록 실패: ${res.status}`)
      toast.success('장비 등록 완료')
      await fetchResults(selectedScanId)
      window.dispatchEvent(new CustomEvent('devices:changed'))
    } catch (err) {
      const msg = err instanceof Error ? err.message : '등록 오류'
      toast.error('장비 등록 실패', { description: msg })
    } finally {
      setActiveActionId(null)
    }
  }

  const handleRegister = async (device: DiscoveredDevice) => {
    const consistency = device.llm_profile?.consistency_result
    if (consistency && !consistency.consistent) {
      const defaultPort = (device.open_ports || []).find((p) => [554, 80, 443, 502].includes(p)) || 554
      setManualDialog({
        open: true,
        deviceId: device.id,
        deviceType: device.llm_profile?.device_type || '',
        manufacturer: device.llm_profile?.manufacturer || '',
        protocol: device.llm_profile?.protocol || '',
        port: String(defaultPort),
        location: 'Auto-Discovered',
        mismatches: (consistency.mismatches || []).map((m) => ({
          field: m.field,
          evidence: m.evidence,
        })),
      })
      return
    }
    await doRegister(device.id, { location: 'Auto-Discovered', status: 'online' })
  }

  const handleManualRegister = async () => {
    if (!manualDialog.deviceId) return
    await doRegister(manualDialog.deviceId, {
      location: manualDialog.location,
      status: 'online',
      manual_override: true,
      device_type: manualDialog.deviceType,
      manufacturer: manualDialog.manufacturer,
      protocol: manualDialog.protocol,
      port: Number(manualDialog.port),
    })
    setManualDialog((prev) => ({ ...prev, open: false }))
  }

  return (
    <>
      <Header fixed>
        <div className='flex w-full items-center justify-between'>
          <div className='flex items-center gap-2'>
            <Radar className='size-5 text-primary' />
            <h1 className='text-lg font-semibold'>네트워크 디스커버리</h1>
            <Badge variant='secondary'>{scans.length} scans</Badge>
          </div>
          <div className='flex items-center gap-2'>
            <Input
              value={cidr}
              onChange={(e) => setCidr(e.target.value)}
              className='w-52'
              placeholder='192.168.1.0/24'
            />
            <Button variant='outline' size='sm' onClick={handleRefresh} disabled={isRefreshing}>
              {isRefreshing ? <Loader2 className='size-4 animate-spin' /> : <RefreshCcw className='size-4' />}
              새로고침
            </Button>
            <Button size='sm' onClick={handleStartScan} disabled={isStarting}>
              {isStarting ? <Loader2 className='size-4 animate-spin' /> : <Search className='size-4' />}
              스캔 시작
            </Button>
          </div>
        </div>
      </Header>

      <Main>
        <div className='grid gap-4 lg:grid-cols-[360px_1fr]'>
          <Card>
            <CardHeader>
              <CardTitle>스캔 세션</CardTitle>
              <CardDescription>최근 네트워크 탐색 이력</CardDescription>
            </CardHeader>
            <CardContent className='space-y-2'>
              {scans.length === 0 ? (
                <p className='text-sm text-muted-foreground'>아직 스캔 이력이 없습니다.</p>
              ) : (
                scans.map((scan) => (
                  <button
                    key={scan.scan_id}
                    type='button'
                    onClick={() => setSelectedScanId(scan.scan_id)}
                    className={`w-full rounded-md border p-3 text-left transition-colors ${
                      selectedScanId === scan.scan_id
                        ? 'border-primary bg-primary/5'
                        : 'hover:bg-muted/50'
                    }`}
                  >
                    <div className='flex items-center justify-between gap-2'>
                      <p className='text-sm font-medium'>{scan.cidr}</p>
                      <Badge variant='outline'>{scan.status}</Badge>
                    </div>
                    <p className='mt-1 text-xs text-muted-foreground'>
                      found: {scan.total_found ?? 0} · {scan.scan_id.slice(0, 8)}
                    </p>
                  </button>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>발견된 장비</CardTitle>
              <CardDescription>
                {selectedScan
                  ? `${selectedScan.cidr} / ${selectedScan.status} / ${devices.length} devices`
                  : '스캔을 선택하세요'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!selectedScanId ? (
                <p className='text-sm text-muted-foreground'>먼저 스캔 세션을 선택해주세요.</p>
              ) : devices.length === 0 ? (
                <p className='text-sm text-muted-foreground'>발견된 장비가 없습니다.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>IP</TableHead>
                      <TableHead>Vendor</TableHead>
                      <TableHead>Ports</TableHead>
                      <TableHead>Profile</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className='text-right'>Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {devices.map((device) => (
                      <TableRow key={device.id}>
                        <TableCell className='font-medium'>{device.ip_address}</TableCell>
                        <TableCell>{device.vendor || '-'}</TableCell>
                        <TableCell>{(device.open_ports || []).join(', ') || '-'}</TableCell>
                        <TableCell>
                          {device.llm_profile ? (
                            <div className='space-y-1 text-xs'>
                              <div className='font-medium'>
                                {device.llm_profile.device_type || 'Unknown'}
                              </div>
                              {device.llm_profile.manufacturer && (
                                <div className='text-muted-foreground'>
                                  {device.llm_profile.manufacturer}
                                  {device.llm_profile.model_name && ` · ${device.llm_profile.model_name}`}
                                </div>
                              )}
                              {device.llm_profile.protocol && (
                                <div className='text-muted-foreground'>
                                  {device.llm_profile.protocol}
                                </div>
                              )}
                              <div className='text-muted-foreground'>
                                신뢰도: {Math.round((device.llm_profile.confidence || 0) * 100)}%
                              </div>
                              {device.llm_profile.reasoning && (
                                <div className='max-w-48 truncate text-muted-foreground' title={device.llm_profile.reasoning}>
                                  {device.llm_profile.reasoning}
                                </div>
                              )}
                              {device.llm_profile.consistency_result ? (
                                device.llm_profile.consistency_result.consistent ? (
                                  <Badge variant='default' className='text-xs'>
                                    ✓ 검증 통과
                                  </Badge>
                                ) : (
                                  <div className='space-y-1'>
                                    <Badge variant='destructive' className='text-xs'>
                                      ⚠ 정합성 불일치
                                    </Badge>
                                    <Button
                                      size='sm'
                                      variant='ghost'
                                      className='h-6 px-2 text-xs'
                                      onClick={() => handleProfile(device.id)}
                                      disabled={activeActionId === device.id}
                                    >
                                      재검증
                                    </Button>
                                  </div>
                                )
                              ) : (
                                <Badge variant='secondary' className='text-xs'>
                                  미검증
                                </Badge>
                              )}
                            </div>
                          ) : (
                            '-'
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge variant='outline'>{device.status}</Badge>
                        </TableCell>
                        <TableCell>
                          <div className='flex items-center justify-end gap-1'>
                            <Button
                              size='sm'
                              variant='outline'
                              onClick={() => handleProfile(device.id)}
                              disabled={activeActionId === device.id}
                            >
                              <Sparkles className='size-3.5' />
                              프로파일
                            </Button>
                            <Button
                              size='sm'
                              onClick={() => handleRegister(device)}
                              disabled={activeActionId === device.id || device.status === 'registered'}
                            >
                              {activeActionId === device.id ? (
                                <Loader2 className='size-3.5 animate-spin' />
                              ) : (
                                <Plus className='size-3.5' />
                              )}
                              등록
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
        </div>

        <Dialog
          open={manualDialog.open}
          onOpenChange={(open) => setManualDialog((prev) => ({ ...prev, open }))}
        >
          <DialogContent className='sm:max-w-lg'>
            <DialogHeader>
              <DialogTitle>장비 정보 확인 후 등록</DialogTitle>
              <DialogDescription>
                정합성 검증에서 불일치가 발견되었습니다. 아래 정보를 확인하고 수정해주세요.
              </DialogDescription>
            </DialogHeader>

            {manualDialog.mismatches.length > 0 && (
              <div className='space-y-2 rounded-md border border-destructive/30 bg-destructive/5 p-3'>
                <p className='flex items-center gap-1.5 text-sm font-medium text-destructive'>
                  <AlertTriangle className='size-4' />
                  불일치 항목
                </p>
                {manualDialog.mismatches.map((m) => (
                  <div key={m.field} className='text-xs text-destructive/80'>
                    <span className='font-medium'>{m.field}</span>: {m.evidence}
                  </div>
                ))}
              </div>
            )}

            <div className='grid gap-4 py-2'>
              <div className='grid gap-2'>
                <Label htmlFor='manual-device-type'>장비 유형</Label>
                <Select
                  value={manualDialog.deviceType}
                  onValueChange={(v) =>
                    setManualDialog((prev) => ({ ...prev, deviceType: v }))
                  }
                >
                  <SelectTrigger className='w-full'>
                    <SelectValue placeholder='장비 유형 선택' />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='CCTV'>CCTV</SelectItem>
                    <SelectItem value='ACU'>ACU</SelectItem>
                    <SelectItem value='NVR'>NVR</SelectItem>
                    <SelectItem value='Sensor'>Sensor</SelectItem>
                    <SelectItem value='기타'>기타</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className='grid gap-2'>
                <Label htmlFor='manual-manufacturer'>제조사</Label>
                <Input
                  id='manual-manufacturer'
                  value={manualDialog.manufacturer}
                  onChange={(e) =>
                    setManualDialog((prev) => ({
                      ...prev,
                      manufacturer: e.target.value,
                    }))
                  }
                  placeholder='제조사 입력'
                />
              </div>

              <div className='grid gap-2'>
                <Label htmlFor='manual-protocol'>프로토콜</Label>
                <Select
                  value={manualDialog.protocol}
                  onValueChange={(v) =>
                    setManualDialog((prev) => ({ ...prev, protocol: v }))
                  }
                >
                  <SelectTrigger className='w-full'>
                    <SelectValue placeholder='프로토콜 선택' />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='RTSP'>RTSP</SelectItem>
                    <SelectItem value='HTTP'>HTTP</SelectItem>
                    <SelectItem value='HTTPS'>HTTPS</SelectItem>
                    <SelectItem value='Modbus'>Modbus</SelectItem>
                    <SelectItem value='ONVIF'>ONVIF</SelectItem>
                    <SelectItem value='기타'>기타</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className='grid gap-2'>
                <Label htmlFor='manual-port'>포트</Label>
                <Input
                  id='manual-port'
                  type='number'
                  value={manualDialog.port}
                  onChange={(e) =>
                    setManualDialog((prev) => ({
                      ...prev,
                      port: e.target.value,
                    }))
                  }
                  placeholder='포트 번호'
                />
              </div>

              <div className='grid gap-2'>
                <Label htmlFor='manual-location'>설치 위치</Label>
                <Input
                  id='manual-location'
                  value={manualDialog.location}
                  onChange={(e) =>
                    setManualDialog((prev) => ({
                      ...prev,
                      location: e.target.value,
                    }))
                  }
                  placeholder='설치 위치'
                />
              </div>
            </div>

            <DialogFooter>
              <Button
                variant='outline'
                onClick={() =>
                  setManualDialog((prev) => ({ ...prev, open: false }))
                }
              >
                취소
              </Button>
              <Button
                onClick={handleManualRegister}
                disabled={activeActionId === manualDialog.deviceId}
              >
                {activeActionId === manualDialog.deviceId ? (
                  <Loader2 className='size-4 animate-spin' />
                ) : (
                  <Plus className='size-4' />
                )}
                확인 후 등록
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </Main>
    </>
  )
}
