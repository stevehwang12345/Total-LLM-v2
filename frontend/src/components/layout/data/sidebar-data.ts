import {
  MessageSquare,
  Camera,
  Monitor,
  Bell,
  FileText,
  BarChart3,
  Shield,
} from 'lucide-react'
import { type SidebarData } from '../types'

export const sidebarData: SidebarData = {
  user: {
    name: '관리자',
    email: 'admin@total-llm.kr',
    avatar: '/avatars/shadcn.jpg',
  },
  teams: [
    {
      name: 'Total-LLM',
      logo: Shield,
      plan: '보안 모니터링',
    },
  ],
  navGroups: [
    {
      title: '주요 기능',
      items: [
        {
          title: '채팅',
          url: '/chat',
          icon: MessageSquare,
        },
        {
          title: '영상 분석',
          url: '/analysis',
          icon: Camera,
        },
        {
          title: '장비 관리',
          url: '/devices',
          icon: Monitor,
        },
        {
          title: '알람',
          url: '/alarms',
          icon: Bell,
        },
        {
          title: '문서 관리',
          url: '/documents',
          icon: FileText,
        },
        {
          title: '리포트',
          url: '/reports',
          icon: BarChart3,
        },
      ],
    },
  ],
}
