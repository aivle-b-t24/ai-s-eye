import React, { useState, useEffect } from 'react'
import { fetchStoreMenus, fetchStorePolicies } from '../../api/storeApi'
import MenuListPanel from './MenuListPanel'
import PolicyListPanel from './PolicyListPanel'
import RoleBanner from '../common/RoleBanner'
import StoreChatbotWidget from './StoreChatbotWidget'

export default function KosStoreManagementView({
  page,
  storeName,
  dashboard,
  soldOutCount,
  apiBaseUrl,
  error,
  loading,
  isChatbotEnabled,
}) {
  const [isPolicyExpanded, setIsPolicyExpanded] = useState(true)
  const [isMenuExpanded, setIsMenuExpanded] = useState(true)

  // 1. 실시간 백엔드 메뉴 및 정책 데이터 저장 상태
  const [menus, setMenus] = useState(dashboard?.menus ?? [])
  const [policies, setPolicies] = useState(dashboard?.policies ?? [])
  const currentStoreId = page?.startsWith('store') ? page : 'store-001'

  // 2. 메뉴 & 정책 백엔드 API 경로 (/api/stores/${storeId}/menus, /api/stores/${storeId}/policies) 로딩
  useEffect(() => {
    async function loadKosData() {
      try {
        const [menuRes, policyRes] = await Promise.all([
          fetchStoreMenus(currentStoreId),
          fetchStorePolicies(currentStoreId),
        ])
        if (menuRes?.menus) setMenus(menuRes.menus)
        if (policyRes?.policies) setPolicies(policyRes.policies)
      } catch (err) {
        console.error('메뉴 & 정책 API 로딩 오류:', err)
      }
    }
    loadKosData()
  }, [currentStoreId])

  return (
    <section className="store-dashboard-view kos-management-view">
      <RoleBanner
        page={page}
        storeName={storeName}
        apiBaseUrl={apiBaseUrl}
        error={error}
        loading={loading}
      />

      <div className="kos-page-header">
        <div>
          <p className="eyebrow">SMART STORE MANAGEMENT</p>
          <h2>스마트 매장 관리 (메뉴와 정책 관리)</h2>
          <p className="kos-page-subtitle">
            매장의 품절 메뉴 현황 관리 및 고객 안내 정책을 실시간으로 확인하고 관리합니다.
          </p>
        </div>
      </div>

      <section className="dashboard-bottom-grid kos-grid">
        <div className="dashboard-feature">
          <PolicyListPanel
            policies={policies}
            isExpanded={isPolicyExpanded}
            onToggleExpand={() => setIsPolicyExpanded((prev) => !prev)}
          />
        </div>

        <div className="dashboard-feature">
          <MenuListPanel
            menus={menus}
            soldOutCount={soldOutCount}
            isExpanded={isMenuExpanded}
            onToggleExpand={() => setIsMenuExpanded((prev) => !prev)}
          />
        </div>
      </section>

      {isChatbotEnabled && (
        {isChatbotEnabled !== false && (
          <StoreChatbotWidget page={currentStoreId} storeName={storeName} />
        )}
      )}
    </section>
  )
}