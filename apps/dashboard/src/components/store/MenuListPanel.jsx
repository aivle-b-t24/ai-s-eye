import React, { useState } from 'react'
import { createStoreMenu, updateStoreMenu, toggleStoreMenuSoldOut, deleteStoreMenu, fetchStoreMenus } from '../../api/storeApi'

const CATEGORY_LABELS = {
  coffee: '커피',
  beverage: '음료/라떼',
  bakery: '베이커리',
  dessert: '디저트',
  tea: '티/에이드',
  general: '기타',
}

export default function MenuListPanel({ storeId = 'store-001', menus = [], setMenus, soldOutCount, isExpanded, onToggleExpand }) {
  const INITIAL_COUNT = 4

  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingMenu, setEditingMenu] = useState(null)
  const [formData, setFormData] = useState({
    category: 'coffee',
    name: '',
    price: '',
    prep_minutes: 3,
    available: true,
    sold_out_reason: '',
  })
  const [loading, setLoading] = useState(false)
  const [togglingMenuId, setTogglingMenuId] = useState(null)
  const [error, setError] = useState(null)

  const displayMenus = isExpanded ? menus : menus?.slice(0, INITIAL_COUNT)
  const hasMore = (menus?.length ?? 0) > INITIAL_COUNT

  const calculatedSoldOutCount = soldOutCount ?? (menus?.filter((m) => !m.available).length || 0)

  const reloadMenus = async () => {
    try {
      const res = await fetchStoreMenus(storeId)
      if (res?.menus && setMenus) {
        setMenus(res.menus)
      }
    } catch (err) {
      console.error('메뉴 목록 새로고침 실패:', err)
    }
  }

  const handleToggleSoldOut = async (menu) => {
    const nextAvailable = !menu.available
    let reason = null
    if (!nextAvailable) {
      const inputReason = window.prompt(`'${menu.name}' 메뉴의 품절 사유를 입력하세요 (선택):`, '재고 소진')
      if (inputReason === null) return // 취소 누름
      reason = inputReason.trim() || '재고 소진'
    }

    try {
      setTogglingMenuId(menu.menu_id)
      // 로컬 Optimistic Update
      if (setMenus) {
        setMenus((prev) =>
          prev.map((m) =>
            m.menu_id === menu.menu_id ? { ...m, available: nextAvailable, sold_out_reason: reason } : m,
          ),
        )
      }
      await toggleStoreMenuSoldOut(storeId, menu.menu_id, nextAvailable, reason)
      await reloadMenus()
    } catch (err) {
      alert(`품절 상태 변경 실패: ${err.message}`)
      await reloadMenus()
    } finally {
      setTogglingMenuId(null)
    }
  }

  const handleOpenAdd = () => {
    setEditingMenu(null)
    setFormData({
      category: 'coffee',
      name: '',
      price: '',
      prep_minutes: 3,
      available: true,
      sold_out_reason: '',
    })
    setError(null)
    setIsModalOpen(true)
  }

  const handleOpenEdit = (menu) => {
    setEditingMenu(menu)
    setFormData({
      category: menu.category || 'coffee',
      name: menu.name || '',
      price: menu.price ?? '',
      prep_minutes: menu.prep_minutes ?? 3,
      available: menu.available ?? true,
      sold_out_reason: menu.sold_out_reason || '',
    })
    setError(null)
    setIsModalOpen(true)
  }

  const handleDelete = async (menuId, name) => {
    if (!window.confirm(`'${name}' 메뉴를 정말 삭제하시겠습니까?`)) return
    try {
      setLoading(true)
      await deleteStoreMenu(storeId, menuId)
      await reloadMenus()
    } catch (err) {
      alert(`메뉴 삭제 실패: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!formData.name.trim()) {
      setError('메뉴명을 입력해 주세요.')
      return
    }
    const priceNum = parseInt(formData.price, 10)
    if (isNaN(priceNum) || priceNum < 0) {
      setError('올바른 가격을 입력해 주세요.')
      return
    }

    const payload = {
      category: formData.category,
      name: formData.name.trim(),
      price: priceNum,
      prep_minutes: parseInt(formData.prep_minutes, 10) || 3,
      available: formData.available,
      sold_out_reason: formData.available ? null : formData.sold_out_reason.trim() || '일시 품절',
    }

    try {
      setLoading(true)
      setError(null)
      if (editingMenu) {
        await updateStoreMenu(storeId, editingMenu.menu_id, payload)
      } else {
        await createStoreMenu(storeId, payload)
      }
      setIsModalOpen(false)
      await reloadMenus()
    } catch (err) {
      setError(`저장 실패: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <article className="panel menu-list-panel">
      <div className="panel-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <p className="eyebrow">Menu Status</p>
          <h2>메뉴 및 품절 현황</h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className="sold-out-badge" style={{ padding: '4px 10px', borderRadius: '12px', fontSize: '12px', fontWeight: '700' }}>
            {calculatedSoldOutCount}개 품절
          </span>
          <button
            type="button"
            className="menu-add-btn"
            onClick={handleOpenAdd}
            style={{
              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
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
              boxShadow: '0 2px 4px rgba(5, 150, 105, 0.2)',
            }}
          >
            + 메뉴 추가
          </button>
        </div>
      </div>

      <div className="menu-list">
        {!menus || menus.length === 0 ? (
          <div className="empty-message">등록된 메뉴가 없습니다. 새 메뉴를 추가해 주세요.</div>
        ) : (
          displayMenus.map((menu) => (
            <div
              className="menu-row"
              key={menu.menu_id}
              style={{
                display: 'flex',
                justify: 'space-between',
                alignItems: 'center',
                padding: '12px 14px',
                marginBottom: '8px',
                borderRadius: '10px',
                background: menu.available ? 'rgba(255, 255, 255, 0.03)' : 'rgba(239, 68, 68, 0.08)',
                border: menu.available ? '1px solid rgba(255, 255, 255, 0.08)' : '1px solid rgba(239, 68, 68, 0.25)',
                transition: 'all 0.2s ease',
              }}
            >
              <div className="menu-info" style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span
                    style={{
                      fontSize: '10px',
                      color: '#94a3b8',
                      background: 'rgba(255, 255, 255, 0.08)',
                      padding: '1px 6px',
                      borderRadius: '4px',
                    }}
                  >
                    {CATEGORY_LABELS[menu.category] || menu.category}
                  </span>
                  <strong style={{ fontSize: '15px', color: menu.available ? '#f8fafc' : '#cbd5e1' }}>
                    {menu.name}
                  </strong>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="menu-price" style={{ fontSize: '13px', fontWeight: '600', color: '#38bdf8' }}>
                    {menu.price.toLocaleString('ko-KR')}원
                  </span>
                  {!menu.available && menu.sold_out_reason && (
                    <span style={{ fontSize: '11px', color: '#fca5a5' }}>
                      ({menu.sold_out_reason})
                    </span>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {/* 1-Click 품절 토글 버튼 */}
                <button
                  type="button"
                  disabled={togglingMenuId === menu.menu_id}
                  onClick={() => handleToggleSoldOut(menu)}
                  style={{
                    background: menu.available
                      ? 'rgba(16, 185, 129, 0.15)'
                      : 'rgba(239, 68, 68, 0.25)',
                    border: menu.available
                      ? '1px solid rgba(16, 185, 129, 0.4)'
                      : '1px solid rgba(239, 68, 68, 0.5)',
                    color: menu.available ? '#6ee7b7' : '#fca5a5',
                    borderRadius: '20px',
                    padding: '5px 12px',
                    fontSize: '12px',
                    fontWeight: '700',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    transition: 'all 0.2s ease',
                  }}
                  title="클릭하여 판매 중 / 품절 상태 전환"
                >
                  <span
                    style={{
                      display: 'inline-block',
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      backgroundColor: menu.available ? '#10b981' : '#ef4444',
                    }}
                  />
                  {menu.available ? '판매 중' : '품절'}
                </button>

                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    type="button"
                    onClick={() => handleOpenEdit(menu)}
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
                    onClick={() => handleDelete(menu.menu_id, menu.name)}
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

      {/* 메뉴 추가/수정 모달 */}
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
              maxWidth: '460px',
              padding: '24px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
              color: '#f8fafc',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 16px 0', fontSize: '18px', fontWeight: '700' }}>
              {editingMenu ? '메뉴 정보 수정' : '새 메뉴 등록'}
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
                  <option value="coffee">커피 (Coffee)</option>
                  <option value="beverage">음료 / 라떼 (Beverage)</option>
                  <option value="bakery">베이커리 (Bakery)</option>
                  <option value="dessert">디저트 (Dessert)</option>
                  <option value="tea">티 / 에이드 (Tea)</option>
                  <option value="general">기타 (General)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: '#94a3b8', marginBottom: '4px' }}>메뉴명</label>
                <input
                  type="text"
                  placeholder="예: 아이스 아메리카노"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
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

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: '#94a3b8', marginBottom: '4px' }}>가격 (원)</label>
                  <input
                    type="number"
                    placeholder="4500"
                    value={formData.price}
                    onChange={(e) => setFormData({ ...formData, price: e.target.value })}
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
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: '#94a3b8', marginBottom: '4px' }}>조리시간 (분)</label>
                  <input
                    type="number"
                    placeholder="3"
                    value={formData.prep_minutes}
                    onChange={(e) => setFormData({ ...formData, prep_minutes: e.target.value })}
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
              </div>

              <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', color: '#f8fafc' }}>
                  <input
                    type="checkbox"
                    checked={formData.available}
                    onChange={(e) => setFormData({ ...formData, available: e.target.checked })}
                  />
                  현재 판매 중 (체크 해제 시 품절)
                </label>
              </div>

              {!formData.available && (
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: '#94a3b8', marginBottom: '4px' }}>품절 사유 (선택)</label>
                  <input
                    type="text"
                    placeholder="예: 원두 재고 소진, 시럽 품절"
                    value={formData.sold_out_reason}
                    onChange={(e) => setFormData({ ...formData, sold_out_reason: e.target.value })}
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
              )}

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
                    background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
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
