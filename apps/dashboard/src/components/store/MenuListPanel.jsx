import React from 'react';

export default function MenuListPanel({ menus, soldOutCount }) {
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
          menus.map((menu) => (
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
    </article>
  );
}
