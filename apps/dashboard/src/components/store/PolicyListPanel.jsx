import React, { useState } from 'react'
import { createStorePolicy, updateStorePolicy, deleteStorePolicy, fetchStorePolicies } from '../../api/storeApi'

const CATEGORY_LABELS = {
  operation: '영업/운영',
  facility: '시설/주차',
  order: '주문/환불',
  general: '기타/안내',
}

const CATEGORY_COLORS = {
  operation: '#3b82f6',
  facility: '#10b981',
  order: '#f59e0b',
  general: '#8b5cf6',
}

export default function PolicyListPanel({ storeId = 'store-001', policies = [], setPolicies, isExpanded, onToggleExpand }) {
  const INITIAL_COUNT = 4

  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingPolicy, setEditingPolicy] = useState(null)
  const [formData, setFormData] = useState({
    category: 'general',
    title: '',
    content: '',
    keywords: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const displayPolicies = isExpanded ? policies : policies?.slice(0, INITIAL_COUNT)
  const hasMore = (policies?.length ?? 0) > INITIAL_COUNT

  const reloadPolicies = async () => {
    try {
      const res = await fetchStorePolicies(storeId)
      if (res?.policies && setPolicies) {
        setPolicies(res.policies)
      }
    } catch (err) {
      console.error('정책 새로고침 실패:', err)
    }
  }

  const handleOpenAdd = () => {
    setEditingPolicy(null)
    setFormData({
      category: 'general',
      title: '',
      content: '',
      keywords: '',
    })
    setError(null)
    setIsModalOpen(true)
  }

  const handleOpenEdit = (policy) => {
    setEditingPolicy(policy)
    setFormData({
      category: policy.category || 'general',
      title: policy.title || '',
      content: policy.content || '',
      keywords: Array.isArray(policy.keywords) ? policy.keywords.join(', ') : '',
    })
    setError(null)
    setIsModalOpen(true)
  }

  const handleDelete = async (policyId, title) => {
    if (!window.confirm(`'${title}' 정책을 삭제하시겠습니까?`)) return
    try {
      setLoading(true)
      await deleteStorePolicy(storeId, policyId)
      await reloadPolicies()
    } catch (err) {
      alert(`정책 삭제 실패: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!formData.title.trim() || !formData.content.trim()) {
      setError('제목과 내용은 필수 입력 항목입니다.')
      return
    }

    const payload = {
      category: formData.category,
      title: formData.title.trim(),
      content: formData.content.trim(),
      keywords: formData.keywords
        .split(',')
        .map((k) => k.trim())
        .filter(Boolean),
    }

    try {
      setLoading(true)
      setError(null)
      if (editingPolicy) {
        await updateStorePolicy(storeId, editingPolicy.policy_id, payload)
      } else {
        await createStorePolicy(storeId, payload)
      }
      setIsModalOpen(false)
      await reloadPolicies()
    } catch (err) {
      setError(`저장 실패: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <article className="panel policy-list-panel">
      <div className="panel-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <p className="eyebrow">Notice & Policy</p>
          <h2>매장 안내 및 정책</h2>
        </div>
        <button
          type="button"
          className="policy-add-btn"
          onClick={handleOpenAdd}
          style={{
            background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
            color: '#ffffff',
            border: 'none',
            borderRadius: '8px',
            padding: '8px 14px',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            boxShadow: '0 2px 4px rgba(37, 99, 235, 0.2)',
          }}
        >
          + 정책 추가
        </button>
      </div>

      <div className="policy-list">
        {!policies || policies.length === 0 ? (
          <div className="empty-message">등록된 매장 정책이 없습니다. 정책을 추가해 주세요.</div>
        ) : (
          displayPolicies.map((policy) => (
            <div
              className="policy-item"
              key={policy.policy_id}
              style={{
                position: 'relative',
                padding: '14px',
                marginBottom: '10px',
                borderRadius: '10px',
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: '700',
                        padding: '2px 8px',
                        borderRadius: '12px',
                        color: '#fff',
                        backgroundColor: CATEGORY_COLORS[policy.category] || CATEGORY_COLORS.general,
                      }}
                    >
                      {CATEGORY_LABELS[policy.category] || '기타'}
                    </span>
                    <strong style={{ fontSize: '15px', fontWeight: '600' }}>{policy.title}</strong>
                  </div>
                  <p style={{ margin: 0, fontSize: '13px', color: '#cbd5e1', lineHeight: '1.5' }}>{policy.content}</p>

                  {Array.isArray(policy.keywords) && policy.keywords.length > 0 && (
                    <div style={{ marginTop: '8px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {policy.keywords.map((kw, idx) => (
                        <span
                          key={idx}
                          style={{
                            fontSize: '11px',
                            color: '#94a3b8',
                            background: 'rgba(255, 255, 255, 0.05)',
                            padding: '1px 6px',
                            borderRadius: '4px',
                          }}
                        >
                          #{kw}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '6px', shrink: 0 }}>
                  <button
                    type="button"
                    onClick={() => handleOpenEdit(policy)}
                    style={{
                      background: 'rgba(255, 255, 255, 0.08)',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      borderRadius: '6px',
                      padding: '4px 8px',
                      fontSize: '12px',
                      color: '#93c5fd',
                      cursor: 'pointer',
                    }}
                  >
                    수정
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(policy.policy_id, policy.title)}
                    style={{
                      background: 'rgba(239, 68, 68, 0.15)',
                      border: '1px solid rgba(239, 68, 68, 0.3)',
                      borderRadius: '6px',
                      padding: '4px 8px',
                      fontSize: '12px',
                      color: '#fca5a5',
                      cursor: 'pointer',
                    }}
                  >
                    삭제
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {hasMore && (
        <div style={{ textAlign: 'center', marginTop: '16px', paddingTop: '12px', paddingBottom: '14px', marginBottom: '4px', borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <button
            type="button"
            onClick={onToggleExpand}
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.18)',
              borderRadius: '20px',
              padding: '7px 20px',
              color: '#f8fafc',
              fontSize: '13px',
              fontWeight: '600',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.2s ease',
            }}
          >
            {isExpanded ? '접기 ▲' : '더보기 ▼'}
          </button>
        </div>
      )}

      {/* 정책 추가/수정 모달 */}
      {isModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '16px',
          }}
          onClick={() => setIsModalOpen(false)}
        >
          <div
            style={{
              background: '#1e293b',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              borderRadius: '16px',
              width: '100%',
              maxWidth: '480px',
              padding: '24px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
              color: '#f8fafc',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 16px 0', fontSize: '18px', fontWeight: '700' }}>
              {editingPolicy ? '매장 정책 수정' : '새 매장 정책 등록'}
            </h3>

            {error && (
              <div style={{ background: 'rgba(239, 68, 68, 0.2)', border: '1px solid #ef4444', color: '#fca5a5', padding: '10px', borderRadius: '8px', fontSize: '13px', marginBottom: '16px' }}>
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: '#94a3b8', marginBottom: '4px' }}>카테고리</label>
                <select
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '10px',
                    borderRadius: '8px',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    color: '#f8fafc',
                    fontSize: '14px',
                  }}
                >
                  <option value="operation">영업/운영 (영업시간, 휴무일 등)</option>
                  <option value="facility">시설/주차 (주차장, 와이파이, 화장실)</option>
                  <option value="order">주문/환불 (포장, 환불, 취소 규정)</option>
                  <option value="general">기타/안내 (반려동물, 매장 이용 안내)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: '#94a3b8', marginBottom: '4px' }}>제목</label>
                <input
                  type="text"
                  placeholder="예: 주차 안내, 영업시간"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '10px',
                    borderRadius: '8px',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    color: '#f8fafc',
                    fontSize: '14px',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: '#94a3b8', marginBottom: '4px' }}>내용 (손님 안내 문구)</label>
                <textarea
                  rows={4}
                  placeholder="손님 및 AI 챗봇이 참조할 상세 설명 문구를 적어주세요."
                  value={formData.content}
                  onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '10px',
                    borderRadius: '8px',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    color: '#f8fafc',
                    fontSize: '14px',
                    resize: 'vertical',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: '#94a3b8', marginBottom: '4px' }}>검색 키워드 (쉼표 구분)</label>
                <input
                  type="text"
                  placeholder="예: 주차, 자동차, 무료주차"
                  value={formData.keywords}
                  onChange={(e) => setFormData({ ...formData, keywords: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '10px',
                    borderRadius: '8px',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    color: '#f8fafc',
                    fontSize: '14px',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  style={{
                    padding: '10px 16px',
                    borderRadius: '8px',
                    background: 'rgba(255, 255, 255, 0.1)',
                    border: 'none',
                    color: '#cbd5e1',
                    fontSize: '14px',
                    fontWeight: '600',
                    cursor: 'pointer',
                  }}
                >
                  취소
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  style={{
                    padding: '10px 20px',
                    borderRadius: '8px',
                    background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
                    border: 'none',
                    color: '#ffffff',
                    fontSize: '14px',
                    fontWeight: '600',
                    cursor: 'pointer',
                  }}
                >
                  {loading ? '저장 중…' : '저장'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </article>
  )
}
