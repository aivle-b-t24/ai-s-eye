import { useCallback, useEffect, useState } from 'react'

import { authenticatedFetch } from '../../api/authenticatedFetch'
import './AccountManagementPanel.css'

async function errorMessage(response, fallback) {
  const body = await response.json().catch(() => null)
  return body?.detail ?? `${fallback} (${response.status})`
}

function storeLabel(user) {
  if (user.store_name && user.store_id) {
    return `${user.store_name} (${user.store_id})`
  }
  return user.store_name || user.store_id || '-'
}

export default function AccountManagementPanel({ apiBaseUrl }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [deletingUid, setDeletingUid] = useState('')
  const [passwordUser, setPasswordUser] = useState(null)
  const [passwordSubmitting, setPasswordSubmitting] = useState(false)
  const [passwordForm, setPasswordForm] = useState({ password: '', passwordConfirm: '' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [form, setForm] = useState({
    email: '',
    name: '',
    storeName: '',
    password: '',
    passwordConfirm: '',
  })

  const loadUsers = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const response = await authenticatedFetch(`${apiBaseUrl}/api/admin/users`, {
        signal,
      })
      if (!response.ok) {
        throw new Error(await errorMessage(response, '계정 목록을 불러오지 못했습니다'))
      }
      setUsers(await response.json())
    } catch (loadError) {
      if (loadError.name !== 'AbortError') {
        setError(loadError.message || '계정 목록을 불러오지 못했습니다')
      }
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [apiBaseUrl])

  useEffect(() => {
    const controller = new AbortController()
    loadUsers(controller.signal)
    return () => controller.abort()
  }, [loadUsers])

  const updateField = (event) => {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  const createAccount = async (event) => {
    event.preventDefault()
    if (form.password !== form.passwordConfirm) {
      setError('초기 비밀번호가 일치하지 않습니다')
      setSuccess('')
      return
    }
    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const response = await authenticatedFetch(`${apiBaseUrl}/api/admin/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.email,
          name: form.name,
          store_name: form.storeName,
          password: form.password,
        }),
      })
      if (!response.ok) {
        throw new Error(await errorMessage(response, '점주 계정을 생성하지 못했습니다'))
      }
      const created = await response.json()
      setUsers((current) => [
        ...current.filter((user) => user.uid !== created.uid),
        created,
      ])
      setForm((current) => ({
        ...current,
        email: '',
        name: '',
        storeName: '',
        password: '',
        passwordConfirm: '',
      }))
      setSuccess(
        `${created.email} 점주 계정과 '${created.store_name || created.store_id}' 매장(${created.store_id})을 등록했습니다. 지정한 초기 비밀번호를 점주에게 전달해 주세요.`,
      )
    } catch (createError) {
      setError(createError.message || '점주 계정을 생성하지 못했습니다')
    } finally {
      setSubmitting(false)
    }
  }

  const deleteAccount = async (user) => {
    const confirmed = window.confirm(
      `${user.name} (${user.email}) 계정을 삭제하시겠습니까? 삭제 후에는 로그인할 수 없습니다.`,
    )
    if (!confirmed) return

    setDeletingUid(user.uid)
    setError('')
    setSuccess('')
    try {
      const response = await authenticatedFetch(
        `${apiBaseUrl}/api/admin/users/${encodeURIComponent(user.uid)}`,
        {
          method: 'DELETE',
        },
      )
      if (!response.ok) {
        throw new Error(await errorMessage(response, '점주 계정을 삭제하지 못했습니다'))
      }
      setUsers((current) => current.filter((account) => account.uid !== user.uid))
      setSuccess(`${user.email} 계정을 삭제했습니다.`)
    } catch (deleteError) {
      setError(deleteError.message || '점주 계정을 삭제하지 못했습니다')
    } finally {
      setDeletingUid('')
    }
  }

  const openPasswordChange = (user) => {
    setPasswordUser(user)
    setPasswordForm({ password: '', passwordConfirm: '' })
    setError('')
    setSuccess('')
  }

  const closePasswordChange = () => {
    if (passwordSubmitting) return
    setPasswordUser(null)
    setPasswordForm({ password: '', passwordConfirm: '' })
  }

  const changePassword = async (event) => {
    event.preventDefault()
    if (!passwordUser) return
    if (passwordForm.password !== passwordForm.passwordConfirm) {
      setError('새 비밀번호가 일치하지 않습니다')
      return
    }

    setPasswordSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const response = await authenticatedFetch(
        `${apiBaseUrl}/api/admin/users/${encodeURIComponent(passwordUser.uid)}/password`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: passwordForm.password }),
        },
      )
      if (!response.ok) {
        throw new Error(await errorMessage(response, '비밀번호를 변경하지 못했습니다'))
      }
      setSuccess(`${passwordUser.email} 계정의 비밀번호를 변경했습니다.`)
      setPasswordUser(null)
      setPasswordForm({ password: '', passwordConfirm: '' })
    } catch (passwordError) {
      setError(passwordError.message || '비밀번호를 변경하지 못했습니다')
    } finally {
      setPasswordSubmitting(false)
    }
  }

  const storeManagers = users.filter((user) => user.role === 'store_manager')

  return (
    <section className="account-management-panel" aria-labelledby="account-management-title">
      <div className="account-management-heading">
        <div>
          <p className="supervisor-section-kicker">계정 관리</p>
          <h2 id="account-management-title">점주 계정 발급</h2>
          <p>본사에서 로그인 이메일, 새 매장명, 초기 비밀번호를 함께 지정합니다.</p>
        </div>
        <span>{loading ? '불러오는 중' : `${storeManagers.length}명 등록`}</span>
      </div>

      <form className="account-create-form" onSubmit={createAccount}>
        <label>
          <span>점주 이메일</span>
          <input
            type="email"
            name="email"
            value={form.email}
            onChange={updateField}
            placeholder="owner@aicafe.com"
            autoComplete="off"
            required
            disabled={submitting}
          />
        </label>
        <label>
          <span>이름</span>
          <input
            type="text"
            name="name"
            value={form.name}
            onChange={updateField}
            placeholder="홍길동 점주"
            maxLength={100}
            required
            disabled={submitting}
          />
        </label>
        <label>
          <span>매장명</span>
          <input
            type="text"
            name="storeName"
            value={form.storeName}
            onChange={updateField}
            placeholder="예: 매장 표시명"
            maxLength={100}
            required
            disabled={submitting}
          />
        </label>
        <label>
          <span>초기 비밀번호</span>
          <input
            type="password"
            name="password"
            value={form.password}
            onChange={updateField}
            placeholder="8자 이상"
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
            required
            disabled={submitting}
          />
        </label>
        <label>
          <span>초기 비밀번호 확인</span>
          <input
            type="password"
            name="passwordConfirm"
            value={form.passwordConfirm}
            onChange={updateField}
            placeholder="비밀번호 다시 입력"
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
            required
            disabled={submitting}
          />
        </label>
        <button type="submit" className="supervisor-primary-button" disabled={submitting}>
          {submitting ? '계정 생성 중' : '점주 계정 생성'}
        </button>
      </form>

      {error && <p className="account-management-message is-error" role="alert">{error}</p>}
      {success && <p className="account-management-message is-success" role="status">{success}</p>}

      <div className="account-list-wrap" aria-busy={loading}>
        {loading ? (
          <p>Firebase 계정 목록을 불러오는 중입니다.</p>
        ) : storeManagers.length === 0 ? (
          <p>아직 발급된 점주 계정이 없습니다.</p>
        ) : (
          <table>
            <caption>발급된 점주 계정</caption>
            <thead>
              <tr>
                <th scope="col">점주</th>
                <th scope="col">이메일</th>
                <th scope="col">담당 매장</th>
                <th scope="col">상태</th>
                <th scope="col">관리</th>
              </tr>
            </thead>
            <tbody>
              {storeManagers.map((user) => (
                <tr key={user.uid}>
                  <td>{user.name}</td>
                  <td>{user.email}</td>
                  <td>{storeLabel(user)}</td>
                  <td>{user.disabled ? '사용 중지' : '사용 가능'}</td>
                  <td>
                    <div className="account-row-actions">
                      <button
                        type="button"
                        className="account-password-button"
                        onClick={() => openPasswordChange(user)}
                        disabled={Boolean(deletingUid) || submitting || passwordSubmitting}
                      >
                        비밀번호 변경
                      </button>
                      <button
                        type="button"
                        className="account-delete-button"
                        onClick={() => deleteAccount(user)}
                        disabled={Boolean(deletingUid) || submitting || passwordSubmitting}
                      >
                        {deletingUid === user.uid ? '삭제 중' : '계정 삭제'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {passwordUser && (
        <div className="account-password-backdrop" role="presentation">
          <section
            className="account-password-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="account-password-title"
          >
            <h3 id="account-password-title">점주 비밀번호 변경</h3>
            <p>{passwordUser.name} ({passwordUser.email})</p>
            <form onSubmit={changePassword}>
              <label>
                <span>새 비밀번호</span>
                <input
                  type="password"
                  value={passwordForm.password}
                  onChange={(event) => setPasswordForm((current) => ({
                    ...current,
                    password: event.target.value,
                  }))}
                  minLength={8}
                  maxLength={128}
                  autoComplete="new-password"
                  placeholder="8자 이상"
                  required
                  autoFocus
                  disabled={passwordSubmitting}
                />
              </label>
              <label>
                <span>새 비밀번호 확인</span>
                <input
                  type="password"
                  value={passwordForm.passwordConfirm}
                  onChange={(event) => setPasswordForm((current) => ({
                    ...current,
                    passwordConfirm: event.target.value,
                  }))}
                  minLength={8}
                  maxLength={128}
                  autoComplete="new-password"
                  placeholder="비밀번호 다시 입력"
                  required
                  disabled={passwordSubmitting}
                />
              </label>
              <div className="account-password-actions">
                <button type="button" onClick={closePasswordChange} disabled={passwordSubmitting}>
                  취소
                </button>
                <button type="submit" className="supervisor-primary-button" disabled={passwordSubmitting}>
                  {passwordSubmitting ? '변경 중' : '비밀번호 변경'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </section>
  )
}
