import { createFileRoute } from '@tanstack/react-router'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'

export const Route = createFileRoute('/_authenticated/reports/')({
  component: ReportsPage,
})

function ReportsPage() {
  return (
    <>
      <Header fixed>
        <h1 className='text-lg font-semibold'>리포트</h1>
      </Header>
      <Main>
        <div className='flex flex-col items-center justify-center gap-4 py-20'>
          <span className='text-4xl'>📊</span>
          <h2 className='text-2xl font-bold'>리포트</h2>
          <p className='text-muted-foreground'>준비 중...</p>
        </div>
      </Main>
    </>
  )
}
