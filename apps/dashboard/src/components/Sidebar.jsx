const MENU_ITEMS = [
  { id: 'dashboard', label: '대시보드' },
  { id: 'kos', label: 'KOS 매장 관리' },
  { id: 'monitoring', label: '실시간 모니터링' },
  { id: 'camera', label: 'AI 카메라' },
  { id: 'pos', label: 'POS 현황' },
  { id: 'kds', label: 'KDS 현황' },
  { id: 'report', label: '분석 리포트' },
  { id: 'setting', label: '설정' },
]

function Sidebar({ isOpen, onClose, page, setPage }) {
  const handleMenuClick = (itemId) => {
    if (itemId === 'setting') {
      setPage('setting')
    } else if (itemId === 'kos') {
      setPage('kos')
    } else if (itemId === 'dashboard') {
      setPage('store-001')
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
                (item.id === 'dashboard' &&
                (page === 'store-001' || page === 'store-002' || page === 'head-office')) ||
                (item.id === 'kos' && page === 'kos') ||
                (item.id === 'setting' && page === 'setting')
                  ? 'active'
                  : ''
              }
              onClick={() => handleMenuClick(item.id)}
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