import { useCallback, useEffect, useState } from 'react'

import { authenticatedFetch } from '../../api/authenticatedFetch'
import './AccountManagementPanel.css'

const STORE_OPTIONS = [
  { id: 'store-001', label: '매장 1' },
  { id: 'store-002', label: '매장 2' },
]

async function errorMessage(response, fallback) {
  const body = await response.json().catch(() => null)
  return body?.detail ?? `${fallback} (${response.status})`
}

export default function AccountManagementPanel({ apiBaseUrl }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [form, setForm] = useState({
    email: '',
    name: '',
    storeId: STORE_OPTIONS[0].id,
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
          store_id: form.storeId,
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
      setForm((current) => ({ ...current, email: '', name: '' }))
      setSuccess(
        `${created.email} 계정을 만들었습니다. 점주가 로그인 화면에서 비밀번호 설정 메일을 요청하면 됩니다.`,
      )
    } catch (createError) {
      setError(createError.message || '점주 계정을 생성하지 못했습니다')
    } finally {
      setSubmitting(false)
    }
  }

  const storeManagers = users.filter((user) => user.role === 'store_manager')

  return (
    <section className="account-management-panel" aria-labelledby="account-management-title">
      <div className="account-management-heading">
        <div>
          <p className="supervisor-section-kicker">계정 관리</p>
          <h2 id="account-management-title">점주 계정 발급</h2>
          <p>본사에서 이메일과 담당 매장을 등록하고, 점주가 직접 비밀번호를 설정합니다.</p>
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
          <span>담당 매장</span>
          <select
            name="storeId"
            value={form.storeId}
            onChange={updateField}
            disabled={submitting}
          >
            {STORE_OPTIONS.map((store) => (
              <option key={store.id} value={store.id}>
                {store.label} ({store.id})
              </option>
            ))}
          </select>
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
              </tr>
            </thead>
            <tbody>
              {storeManagers.map((user) => (
                <tr key={user.uid}>
                  <td>{user.name}</td>
                  <td>{user.email}</td>
                  <td>{user.store_id}</td>
                  <td>{user.disabled ? '사용 중지' : '사용 가능'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
