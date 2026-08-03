import { useEffect, useRef, useState } from 'react'

import { authenticatedFetch } from '../api/authenticatedFetch'

function isLocalImage(source) {
  return source?.startsWith('blob:') || source?.startsWith('data:')
}

function decodeImage(source) {
  if (typeof Image === 'undefined') return Promise.resolve()

  const image = new Image()
  if (typeof image.decode === 'function') {
    image.src = source
    return image.decode()
  }

  return new Promise((resolve, reject) => {
    image.onload = resolve
    image.onerror = () => reject(new Error('이미지를 디코딩하지 못했습니다.'))
    image.src = source
  })
}

function revokeAfterSwap(objectUrl) {
  if (!objectUrl) return
  const revoke = () => URL.revokeObjectURL(objectUrl)
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(revoke)
    return
  }
  setTimeout(revoke, 0)
}

export function useAuthenticatedImage(source) {
  const [state, setState] = useState({ src: '', loading: Boolean(source), error: null })
  const displayedObjectUrlRef = useRef(null)
  const requestSequenceRef = useRef(0)

  useEffect(() => {
    const requestSequence = requestSequenceRef.current + 1
    requestSequenceRef.current = requestSequence

    if (!source) {
      const previousObjectUrl = displayedObjectUrlRef.current
      displayedObjectUrlRef.current = null
      setState({ src: '', loading: false, error: null })
      revokeAfterSwap(previousObjectUrl)
      return undefined
    }
    if (isLocalImage(source)) {
      const previousObjectUrl = displayedObjectUrlRef.current
      displayedObjectUrlRef.current = null
      setState({ src: source, loading: false, error: null })
      revokeAfterSwap(previousObjectUrl)
      return undefined
    }

    const controller = new AbortController()
    let objectUrl = null
    let adopted = false
    setState((current) => ({ ...current, loading: true, error: null }))

    authenticatedFetch(source, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`이미지 요청 실패 (${response.status})`)
        return response.blob()
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        return decodeImage(objectUrl)
      })
      .then(() => {
        if (controller.signal.aborted || requestSequence !== requestSequenceRef.current) {
          if (objectUrl) {
            URL.revokeObjectURL(objectUrl)
            objectUrl = null
          }
          return
        }
        const previousObjectUrl = displayedObjectUrlRef.current
        displayedObjectUrlRef.current = objectUrl
        adopted = true
        setState({ src: objectUrl, loading: false, error: null })
        revokeAfterSwap(previousObjectUrl)
      })
      .catch((error) => {
        if (objectUrl && !adopted) {
          URL.revokeObjectURL(objectUrl)
          objectUrl = null
        }
        if (error.name !== 'AbortError') {
          setState((current) => ({ ...current, loading: false, error }))
        }
      })

    return () => {
      controller.abort()
      if (objectUrl && !adopted) URL.revokeObjectURL(objectUrl)
    }
  }, [source])

  useEffect(() => () => {
    requestSequenceRef.current += 1
    if (displayedObjectUrlRef.current) {
      URL.revokeObjectURL(displayedObjectUrlRef.current)
      displayedObjectUrlRef.current = null
    }
  }, [])

  return state
}
