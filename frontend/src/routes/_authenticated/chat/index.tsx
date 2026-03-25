import { useState, useRef, useEffect, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  SendHorizonal,
  Bot,
  User,
  Loader2,
  Sparkles,
  RotateCcw,
} from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Card,
  CardContent,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export const Route = createFileRoute('/_authenticated/chat/')({
  component: ChatPage,
})

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [useRag, setUseRag] = useState(true)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector(
        '[data-slot="scroll-area-viewport"]'
      )
      if (viewport) {
        viewport.scrollTop = viewport.scrollHeight
      }
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [scrollToBottom])

  const handleSend = async () => {
    const trimmed = input.trim()
    if (!trimmed || isLoading) return

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsLoading(true)

    const assistantId = crypto.randomUUID()
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: 'assistant', content: '', timestamp: new Date() },
    ])

    try {
      abortRef.current = new AbortController()
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: trimmed,
          conversation_id: conversationId,
          use_rag: useRag,
        }),
        signal: abortRef.current.signal,
      })

      if (!res.ok) {
        throw new Error(`서버 오류: ${res.status}`)
      }

      const reader = res.body?.getReader()
      if (!reader) throw new Error('스트림을 읽을 수 없습니다')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') continue

          try {
            const parsed = JSON.parse(data)

            if (parsed.conversation_id) {
              setConversationId(parsed.conversation_id)
            }
            if (parsed.content) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: m.content + parsed.content }
                    : m
                )
              )
            }
            if (parsed.done) {
              break
            }
          } catch {
            void 0
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const message = err instanceof Error ? err.message : '알 수 없는 오류'
      toast.error('전송 실패', { description: message })
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: '⚠️ 응답을 받지 못했습니다. 다시 시도해 주세요.' }
            : m
        )
      )
    } finally {
      setIsLoading(false)
      abortRef.current = null
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleNewChat = () => {
    if (abortRef.current) abortRef.current.abort()
    setMessages([])
    setConversationId(null)
    setIsLoading(false)
  }

  return (
    <>
      <Header fixed>
        <div className='flex w-full items-center justify-between'>
          <div className='flex items-center gap-2'>
            <Bot className='size-5 text-primary' />
            <h1 className='text-lg font-semibold'>보안 AI 채팅</h1>
            {conversationId && (
              <Badge variant='outline' className='text-xs font-normal'>
                대화 진행 중
              </Badge>
            )}
          </div>
          <div className='flex items-center gap-4'>
            <div className='flex items-center gap-2'>
              <Switch
                id='rag-mode'
                checked={useRag}
                onCheckedChange={setUseRag}
              />
              <Label htmlFor='rag-mode' className='text-sm'>
                <Sparkles className='mr-1 inline size-3.5' />
                RAG 모드
              </Label>
            </div>
            <Button variant='outline' size='sm' onClick={handleNewChat}>
              <RotateCcw className='size-4' />
              새 대화
            </Button>
          </div>
        </div>
      </Header>
      <Main fixed className='flex flex-col gap-0 p-0'>
        <ScrollArea ref={scrollRef} className='flex-1'>
          <div className='mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-6'>
            {messages.length === 0 && (
              <div className='flex flex-1 flex-col items-center justify-center gap-4 py-20'>
                <div className='flex size-16 items-center justify-center rounded-2xl bg-primary/10'>
                  <Bot className='size-8 text-primary' />
                </div>
                <h2 className='text-xl font-semibold'>
                  보안 AI 어시스턴트
                </h2>
                <p className='max-w-md text-center text-sm text-muted-foreground'>
                  물리보안 시스템에 관한 질문을 입력하세요. CCTV, 출입통제, 알람 관리 등 다양한 보안 관련 질의를 도와드립니다.
                </p>
                <div className='mt-4 grid grid-cols-2 gap-2'>
                  {[
                    'CCTV 이상 감지 시 대응 절차는?',
                    '출입통제 시스템 장애 처리 방법',
                    '야간 경비 순찰 체크리스트',
                    '보안 사고 보고서 작성 방법',
                  ].map((q) => (
                    <Button
                      key={q}
                      variant='outline'
                      size='sm'
                      className='h-auto whitespace-normal px-3 py-2 text-start text-xs'
                      onClick={() => {
                        setInput(q)
                        textareaRef.current?.focus()
                      }}
                    >
                      {q}
                    </Button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  'flex gap-3',
                  msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'
                )}
              >
                <div
                  className={cn(
                    'flex size-8 shrink-0 items-center justify-center rounded-lg',
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground'
                  )}
                >
                  {msg.role === 'user' ? (
                    <User className='size-4' />
                  ) : (
                    <Bot className='size-4' />
                  )}
                </div>
                <Card
                  className={cn(
                    'max-w-[80%] gap-0 py-0',
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted/50'
                  )}
                >
                  <CardContent className='px-4 py-3'>
                    {msg.content ? (
                      <div className='whitespace-pre-wrap text-sm leading-relaxed'>
                        {msg.content}
                      </div>
                    ) : (
                      <div className='flex items-center gap-2 text-sm text-muted-foreground'>
                        <Loader2 className='size-3.5 animate-spin' />
                        생각 중...
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            ))}
          </div>
        </ScrollArea>

        <div className='border-t bg-background/80 backdrop-blur-sm'>
          <div className='mx-auto flex w-full max-w-3xl items-end gap-2 px-4 py-3'>
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder='보안 관련 질문을 입력하세요...'
              className='max-h-32 min-h-10 resize-none'
              disabled={isLoading}
            />
            <Button
              size='icon'
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className='shrink-0'
            >
              {isLoading ? (
                <Loader2 className='size-4 animate-spin' />
              ) : (
                <SendHorizonal className='size-4' />
              )}
            </Button>
          </div>
        </div>
      </Main>
    </>
  )
}
