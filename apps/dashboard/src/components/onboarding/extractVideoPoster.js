/** 영상 중간 지점에서 JPEG 포스터 프레임 Blob을 뽑는다. */
export function extractVideoPoster(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const video = document.createElement('video')
    video.preload = 'auto'
    video.muted = true
    video.playsInline = true
    video.src = url

    const cleanup = () => {
      URL.revokeObjectURL(url)
      video.removeAttribute('src')
      video.load()
    }

    video.onerror = () => {
      cleanup()
      reject(new Error('영상을 읽지 못했습니다.'))
    }

    video.onloadeddata = () => {
      const target = Number.isFinite(video.duration) && video.duration > 0
        ? Math.min(video.duration * 0.2, Math.max(0, video.duration - 0.1))
        : 0
      const seek = () => {
        const canvas = document.createElement('canvas')
        canvas.width = video.videoWidth || 1280
        canvas.height = video.videoHeight || 720
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          cleanup()
          reject(new Error('캔버스를 만들 수 없습니다.'))
          return
        }
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
        canvas.toBlob(
          (blob) => {
            cleanup()
            if (!blob) {
              reject(new Error('대표 프레임을 만들지 못했습니다.'))
              return
            }
            resolve(blob)
          },
          'image/jpeg',
          0.92,
        )
      }
      video.onseeked = seek
      try {
        video.currentTime = target
      } catch {
        seek()
      }
    }
  })
}
