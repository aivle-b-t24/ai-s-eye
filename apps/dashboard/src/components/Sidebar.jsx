import { useNavigate, useLocation } from 'react-router-dom'

import { ROUTES, pageFromPathname } from '../constants/routes'

const MENU_ITEMS = [
  { id: 'dashboard', label: '대시보드', to: ROUTES.DASHBOARD },
  { id: 'onboarding', label: '매장 온보딩', to: ROUTES.ONBOARDING },
  { id: 'kos', label: 'KOS 매장 관리', to: ROUTES.MENUS },
  { id: 'monitoring', label: '실시간 모니터링' },
  { id: 'camera', label: 'AI 카메라' },
  { id: 'pos', label: 'POS 현황' },
  { id: 'kds', label: 'KDS 현황' },
  { id: 'report', label: '분석 리포트' },
  { id: 'setting', label: '설정', to: ROUTES.SETTINGS },
]

function Sidebar({ isOpen, onClose }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const page = pageFromPathname(pathname)

  const handleMenuClick = (item) => {
    if (item.to) {
      navigate(item.to)
    }
    onClose()
  }

  return (
    <>
      <div
        className={`sidebar-backdrop ${isOpen ? 'is-open' : ''}`}
        onClick={onClose}
      />

      <aside className={`side-menu ${isOpen ? 'is-open' : ''}`}>
        <div className="side-menu-header">
          <strong>AI’s Eye</strong>

          <button
            type="button"
            onClick={onClose}
            aria-label="메뉴 닫기"
          >
            ×
          </button>
        </div>

        <nav>
          {MENU_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={
                (item.id === 'dashboard' && page === 'dashboard')
                || (item.id === 'onboarding' && page === 'onboarding')
                || (item.id === 'kos' && page === 'kos')
                || (item.id === 'setting' && page === 'setting')
                  ? 'active'
                  : ''
              }
              onClick={() => handleMenuClick(item)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>
    </>
  )
}

export default Sidebar
