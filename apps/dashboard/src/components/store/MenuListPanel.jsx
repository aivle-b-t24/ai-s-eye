import React from 'react';

export default function MenuListPanel({ menus, soldOutCount, isExpanded, onToggleExpand }) {
  const INITIAL_COUNT = 4;

  const displayMenus = isExpanded ? menus : menus?.slice(0, INITIAL_COUNT);
  const hasMore = (menus?.length ?? 0) > INITIAL_COUNT;

  return (
    <article className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Menu Status</p>
          <h2>메뉴 및 품절 현황</h2>
        </div>
        <span className="sold-out-badge">
          {soldOutCount}개 품절
        </span>
      </div>

      <div className="menu-list">
        {!menus || menus.length === 0 ? (
          <div className="empty-message">등록된 메뉴가 없습니다.</div>
        ) : (
          displayMenus.map((menu) => (
            <div className="menu-row" key={menu.menu_id}>
              <div className="menu-info">
                <strong>{menu.name}</strong>
                <span className="menu-price">{menu.price.toLocaleString("ko-KR")}원</span>
              </div>

              <span
                className={
                  menu.available
                    ? "status available"
                    : "status sold-out"
                }
              >
                {menu.available ? "판매 중" : "품절"}
              </span>
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
              color: '#ffffff',
              fontSize: '13px',
              fontWeight: '600',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.2s ease'
            }}
          >
            {isExpanded ? '접기 ▲' : '더보기 ▼'}
          </button>
        </div>
      )}
    </article>
  );
}


