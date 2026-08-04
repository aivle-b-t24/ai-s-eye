import React, { useState, useEffect } from 'react'

import RoleBanner from '../common/RoleBanner'
import KpiSummaryBar from './KpiSummaryBar'
import ZoneBreakdownTable from './ZoneBreakdownTable'
import StoreChatbotWidget from './StoreChatbotWidget'

export default function StoreDashboardView({
  page,
  storeName,
  dashboard,
  soldOutCount,
  apiBaseUrl,
  error,
  loading,
  isChatbotEnabled,
}) {
  const [isPolicyExpanded, _setIsPolicyExpanded] = useState(false)
  const [isMenuExpanded, _setIsMenuExpanded] = useState(false)

  const isAnyExpanded = isPolicyExpanded || isMenuExpanded

  useEffect(() => {
    const dashContent = document.querySelector('.dashboard-content')
    if (dashContent) {
      if (isAnyExpanded) {
        dashContent.classList.add('is-expanded')
      } else {
        dashContent.classList.remove('is-expanded')
      }
    }
  }, [isAnyExpanded])

  return (

    <section className="store-dashboard-view">
      <RoleBanner
        page={page}
        storeName={storeName}
        apiBaseUrl={apiBaseUrl}
        error={error}
        loading={loading}
      />
      {dashboard?.state?.quality_status !== 'normal' && (
        <section className="alert-banner warning-alert">
          ⚠️ <strong>점주 알림:</strong> AI 카메라 스트림 화질 점검이
          필요합니다.
        </section>
      )}

      {(dashboard?.state?.queue_count_estimate ?? 0) >= 20 && (
        <section className="alert-banner queue-alert">
          🚨 <strong>대기 폭주 알림:</strong> 현재 외부 대기 인원이{' '}
          {dashboard?.state?.queue_count_estimate}명으로 증가했습니다.
          카운터 대응을 권장합니다.
        </section>
      )}

      <section className="dashboard-section">
        <div className="dashboard-section-heading">
          <div>
            <p className="dashboard-section-eyebrow">LIVE OVERVIEW</p>
            <h2>현재 매장 운영 현황</h2>
          </div>

          <span className="dashboard-section-status">
            실시간 업데이트
          </span>
        </div>


        <KpiSummaryBar
          dashboard={dashboard}
          soldOutCount={soldOutCount}
        />
      </section>

      <section className="dashboard-feature-grid">
        <div className="dashboard-feature dashboard-feature-large">
          <ZoneBreakdownTable
            storeId={page}
            zoneCounts={dashboard?.state?.zone_counts}
          />
        </div>
      </section>

      {/* JBNU Inspired Store Chatbot Widget */}
      {isChatbotEnabled !== false && (
        <StoreChatbotWidget page={page} storeName={storeName} />
      )}

    </section>
  )
}
