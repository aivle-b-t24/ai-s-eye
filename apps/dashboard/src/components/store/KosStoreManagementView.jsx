import React, { useState } from 'react'
import MenuListPanel from './MenuListPanel'
import PolicyListPanel from './PolicyListPanel'
import RoleBanner from '../common/RoleBanner'
import StoreChatbotWidget from './StoreChatbotWidget'

export default function KosStoreManagementView({
  page,
  dashboard,
  soldOutCount,
  apiBaseUrl,
  error,
  loading,
  isChatbotEnabled,
}) {
  const [isPolicyExpanded, setIsPolicyExpanded] = useState(true)
  const [isMenuExpanded, setIsMenuExpanded] = useState(true)

  return (
    <section className="store-dashboard-view kos-management-view">
      <RoleBanner
        page={page}
        apiBaseUrl={apiBaseUrl}
        error={error}
        loading={loading}
      />

      <div className="kos-page-header">
        <div>
          <p className="eyebrow">KOS & SMART STORE MANAGEMENT</p>
          <h2>KOS 스마트 매장 관리 (키오스크/POS/메뉴 정책)</h2>
          <p className="kos-page-subtitle">
            매장의 품절 메뉴 현황 관리 및 고객 안내 정책을 실시간으로 확인하고 관리합니다.
          </p>
        </div>
      </div>

      <section className="dashboard-bottom-grid kos-grid">
        <div className="dashboard-feature">
          <PolicyListPanel
            policies={dashboard?.policies}
            isExpanded={isPolicyExpanded}
            onToggleExpand={() => setIsPolicyExpanded((prev) => !prev)}
          />
        </div>

        <div className="dashboard-feature">
          <MenuListPanel
            menus={dashboard?.menus}
            soldOutCount={soldOutCount}
            isExpanded={isMenuExpanded}
            onToggleExpand={() => setIsMenuExpanded((prev) => !prev)}
          />
        </div>
      </section>

      {isChatbotEnabled !== false && <StoreChatbotWidget page={page} />}
    </section>
  )
}
