export function mergeSceneDraft(currentObjects = [], draftObjects = []) {
  const replacedTypes = new Set(draftObjects.map((item) => item.type))
  return [
    ...currentObjects.filter((item) => !replacedTypes.has(item.type)),
    ...draftObjects,
  ]
}

export function sceneSourceLabel(source) {
  if (source === 'ai_assisted') return 'YOLO 보조'
  if (source === 'manual') return '수동 보정'
  return '기본 장면'
}

export async function imageSourceToPayload(source) {
  if (!source) throw new Error('분석할 CCTV 이미지가 없습니다.')
  const response = await fetch(source)
  if (!response.ok) throw new Error(`이미지 준비 실패 (${response.status})`)
  const blob = await response.blob()
  if (!['image/jpeg', 'image/png'].includes(blob.type)) {
    throw new Error('JPEG 또는 PNG 이미지만 YOLO로 분석할 수 있습니다.')
  }
  if (blob.size > 5 * 1024 * 1024) {
    throw new Error('YOLO 분석 이미지는 5MB 이하여야 합니다.')
  }
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('이미지를 읽지 못했습니다.'))
    reader.readAsDataURL(blob)
  })
  return {
    imageBase64: String(dataUrl).split(',', 2)[1],
    mimeType: blob.type,
  }
}
