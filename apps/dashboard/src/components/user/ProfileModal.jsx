import React from 'react'
import { ROLES } from '../../constants/auth'
import { storeDisplayName } from '../../api/storeDirectory'

export default function ProfileModal({ user, onClose, onLogout }) {
  if (!user) return null

  const isStoreManager = user.role === ROLES.STORE_MANAGER
  const storeLabel = isStoreManager
    ? (user.storeName || storeDisplayName(user.storeId))
    : '본사 직속 관제'

  return (
    <div className="profile-modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="profile-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* 상단 닫기 X 버튼 */}
        <button
          type="button"
          className="profile-close-btn"
          onClick={onClose}
          aria-label="프로필 창 닫기"
          title="닫기"
        >
          ✕
        </button>

        {/* 프로필 헤더 바 */}
        <div className="profile-card-header">
          <div className="profile-avatar-circle">
            <span className="avatar-icon">
              {isStoreManager ? '🏪' : '👔'}
            </span>
          </div>
          <div className="profile-title-group">
            <span className="profile-role-badge">
              {isStoreManager ? '가맹점주 프로필' : '본사 슈퍼바이저 프로필'}
            </span>
            <h3 className="profile-user-name">{user.name}</h3>
            <p className="profile-user-id">계정 ID: {user.id}</p>
          </div>
        </div>

        {/* 상세 정보 테이블 리스트 */}
        <div className="profile-info-grid">
          <div className="info-item">
            <span className="info-label">회원 구분 (권한)</span>
            <span className="info-value">
              {isStoreManager ? '가맹점주 (매장 관제)' : '본사 관리자 (슈퍼바이저)'}
            </span>
          </div>

          <div className="info-item">
            <span className="info-label">담당 소속 / 영역</span>
            <span className="info-value highlight">{storeLabel}</span>
          </div>

          <div className="info-item">
            <span className="info-label">연락처 / 이메일</span>
            <span className="info-value">{user.email ?? `${user.id}@aicafe.com`}</span>
          </div>

          <div className="info-item">
            <span className="info-label">시스템 관제 상태</span>
            <span className="info-value status-active">🟢 정상 연동 중 (AI Vision Sync)</span>
          </div>

          <div className="info-item">
            <span className="info-label">최종 세션 접속 시각</span>
            <span className="info-value">2026-07-28 KST (실시간 관제)</span>
          </div>
        </div>

        {/* 푸터 하단 버튼 영역 */}
        <div className="profile-card-footer">
          <button type="button" className="profile-action-btn secondary" onClick={onClose}>
            닫기
          </button>
          <button
            type="button"
            className="profile-action-btn danger"
            onClick={() => {
              onClose()
              onLogout()
            }}
          >
            로그아웃
          </button>
        </div>
      </div>
    </div>
  )
}
