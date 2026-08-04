import assert from 'node:assert/strict'
import test from 'node:test'

import { mergeSceneDraft, sceneSourceLabel } from './sceneSuggestion.js'

test('YOLO 초안은 감지한 테이블만 교체하고 카운터와 구조물은 보존한다', () => {
  const current = [
    { id: 'floor-1', type: 'floor' },
    { id: 'wall-1', type: 'wall' },
    { id: 'table-old', type: 'table' },
    { id: 'counter-old', type: 'counter' },
    { id: 'entrance-1', type: 'entrance' },
  ]
  const draft = [
    { id: 'ai-table-1', type: 'table' },
  ]

  const merged = mergeSceneDraft(current, draft)

  assert.deepEqual(merged.map((item) => item.id), [
    'floor-1',
    'wall-1',
    'counter-old',
    'entrance-1',
    'ai-table-1',
  ])
})

test('장면 설정 이력에서 YOLO 보조 출처를 구분한다', () => {
  assert.equal(sceneSourceLabel('ai_assisted'), 'YOLO 보조')
  assert.equal(sceneSourceLabel('manual'), '수동 보정')
  assert.equal(sceneSourceLabel('default_import'), '기본 장면')
})
