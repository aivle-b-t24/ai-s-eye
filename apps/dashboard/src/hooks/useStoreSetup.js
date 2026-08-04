import { useCallback, useEffect, useState } from 'react'

import { fetchStoreSetupStatus } from '../api/storeSetup'

export function useStoreSetup(storeId) {
  const [setupReady, setSetupReady] = useState(false)
  const [needsOnboarding, setNeedsOnboarding] = useState(false)
  const [setupError, setSetupError] = useState('')

  const refreshSetup = useCallback(async () => {
    if (!storeId) {
      setNeedsOnboarding(false)
      setSetupReady(true)
      setSetupError('')
      return { needsOnboarding: false }
    }

    setSetupReady(false)
    try {
      const status = await fetchStoreSetupStatus(storeId)
      setNeedsOnboarding(status.needsOnboarding)
      setSetupError('')
      setSetupReady(true)
      return status
    } catch (error) {
      setSetupError(error.message || '매장 설정 확인에 실패했습니다.')
      setNeedsOnboarding(false)
      setSetupReady(true)
      return { needsOnboarding: false, error }
    }
  }, [storeId])

  useEffect(() => {
    let cancelled = false
    setSetupReady(false)

    fetchStoreSetupStatus(storeId)
      .then((status) => {
        if (cancelled) return
        setNeedsOnboarding(status.needsOnboarding)
        setSetupError('')
        setSetupReady(true)
      })
      .catch((error) => {
        if (cancelled) return
        setSetupError(error.message || '매장 설정 확인에 실패했습니다.')
        setNeedsOnboarding(false)
        setSetupReady(true)
      })

    return () => {
      cancelled = true
    }
  }, [storeId])

  return {
    setupReady,
    needsOnboarding,
    setupError,
    refreshSetup,
  }
}
