const STORE_ONE_SCENE = {
  storeId: 'store-001',
  cameraId: 'store-001-cam1',
  label: 'CAM 01',
  perspective: {
    far_y: 260,
    near_y: 960,
    far_scale: 0.68,
    near_scale: 1.3,
  },
  bboxScale: {
    reference_height: 0.32,
    weight: 0.68,
    minimum: 0.55,
    maximum: 1.65,
  },
  objects: [
    {
      id: 'wall-back',
      type: 'wall',
      polygon: [[0, 0], [519, 8], [519, 336], [13, 714]],
    },
    {
      id: 'floor-main',
      type: 'floor',
      label: '바닥',
      polygon: [[6, 718], [529, 322], [1000, 517], [886, 980], [0, 1000]],
    },
    {
      id: 'counter-main',
      type: 'counter',
      label: '카운터',
      polygon: [[570, 111], [992, 198], [997, 445], [764, 334], [556, 227]],
    },
    {
      id: 'table-left',
      type: 'table',
      label: '테이블',
      polygon: [[74, 537], [197, 460], [232, 494], [92, 590]],
    },
    {
      id: 'table-center-left',
      type: 'table',
      label: '테이블',
      polygon: [[277, 410], [353, 367], [376, 400], [305, 433]],
    },
    {
      id: 'table-center',
      type: 'table',
      label: '테이블',
      polygon: [[283, 638], [373, 570], [419, 640], [327, 705]],
    },
    {
      id: 'table-group',
      type: 'table',
      label: '테이블',
      polygon: [[416, 282], [465, 252], [499, 282], [440, 312]],
    },
    {
      id: 'table-right',
      type: 'table',
      label: '테이블',
      polygon: [[833, 379], [873, 400], [912, 421], [880, 486], [800, 457]],
    },
    {
      id: 'table-front',
      type: 'table',
      label: '테이블',
      polygon: [[483, 680], [571, 766], [457, 912], [400, 783]],
    },
    {
      id: 'table-middle-right',
      type: 'table',
      label: '테이블',
      polygon: [[590, 344], [683, 419], [724, 370], [643, 307]],
    },
  ],
  seatAnchors: [
    { id: 'table-left-seat-1', table_id: 'table-left', x: 112, y: 628 },
    { id: 'table-left-seat-2', table_id: 'table-left', x: 218, y: 602 },
    { id: 'table-center-left-seat-1', table_id: 'table-center-left', x: 302, y: 470 },
    { id: 'table-center-left-seat-2', table_id: 'table-center-left', x: 375, y: 446 },
    { id: 'table-center-seat-1', table_id: 'table-center', x: 304, y: 752 },
    { id: 'table-center-seat-2', table_id: 'table-center', x: 405, y: 726 },
    { id: 'table-group-seat-1', table_id: 'table-group', x: 428, y: 346 },
    { id: 'table-group-seat-2', table_id: 'table-group', x: 493, y: 330 },
    { id: 'table-middle-right-seat-1', table_id: 'table-middle-right', x: 607, y: 447 },
    { id: 'table-middle-right-seat-2', table_id: 'table-middle-right', x: 701, y: 424 },
    { id: 'table-right-seat-1', table_id: 'table-right', x: 813, y: 515 },
    { id: 'table-right-seat-2', table_id: 'table-right', x: 891, y: 535 },
    { id: 'table-front-seat-1', table_id: 'table-front', x: 410, y: 952 },
    { id: 'table-front-seat-2', table_id: 'table-front', x: 520, y: 930 },
  ],
}

const STORE_TWO_SCENE = {
  storeId: 'store-002',
  cameraId: 'store-002-cam1',
  label: 'CAM 02',
  perspective: {
    far_y: 220,
    near_y: 960,
    far_scale: 0.68,
    near_scale: 1.3,
  },
  bboxScale: {
    reference_height: 0.27,
    weight: 0.68,
    minimum: 0.55,
    maximum: 1.65,
  },
  objects: [
    {
      id: 'wall-back',
      type: 'wall',
      polygon: [[0, 0], [1000, 0], [1000, 390], [0, 390]],
    },
    {
      id: 'floor-main',
      type: 'floor',
      label: '바닥',
      polygon: [[0, 362], [1000, 362], [1000, 997], [0, 997]],
    },
    {
      id: 'counter-main',
      type: 'counter',
      label: '카운터',
      polygon: [[0, 265], [285, 240], [330, 585], [65, 720], [0, 640]],
    },
    {
      id: 'entrance-center',
      type: 'entrance',
      label: '입구',
      polygon: [[269, 250], [379, 220], [382, 402], [291, 426]],
    },
    {
      id: 'table-center',
      type: 'table',
      label: '테이블',
      polygon: [[420, 409], [455, 426], [443, 462], [408, 454]],
    },
    {
      id: 'table-back-right',
      type: 'table',
      label: '테이블',
      polygon: [[509, 366], [539, 333], [619, 384], [607, 429]],
    },
    {
      id: 'table-right',
      type: 'table',
      label: '테이블',
      polygon: [[712, 553], [746, 478], [821, 515], [786, 591]],
    },
    {
      id: 'table-front',
      type: 'table',
      label: '테이블',
      polygon: [[516, 542], [595, 518], [793, 955], [592, 988], [540, 808]],
    },
    {
      id: 'entrance-right',
      type: 'entrance',
      polygon: [[900, 250], [1000, 245], [1000, 520], [875, 439]],
    },
  ],
  seatAnchors: [
    { id: 'table-front-seat-1', table_id: 'table-front', x: 508, y: 681 },
    { id: 'table-front-seat-2', table_id: 'table-front', x: 532, y: 887 },
    { id: 'table-center-seat-1', table_id: 'table-center', x: 241, y: 616 },
    { id: 'table-center-seat-2', table_id: 'table-center', x: 283, y: 512 },
    { id: 'table-center-seat-3', table_id: 'table-center', x: 333, y: 449 },
    { id: 'table-center-seat-4', table_id: 'table-center', x: 359, y: 399 },
    { id: 'table-center-seat-5', table_id: 'table-center', x: 458, y: 500 },
    { id: 'table-center-seat-6', table_id: 'table-center', x: 415, y: 392 },
    { id: 'table-back-right-seat-1', table_id: 'table-back-right', x: 568, y: 473 },
    { id: 'table-center-seat-7', table_id: 'table-center', x: 493, y: 427 },
    { id: 'table-back-right-seat-2', table_id: 'table-back-right', x: 564, y: 342 },
    { id: 'table-back-right-seat-3', table_id: 'table-back-right', x: 619, y: 375 },
    { id: 'table-right-seat-1', table_id: 'table-right', x: 707, y: 600 },
    { id: 'table-right-seat-2', table_id: 'table-right', x: 712, y: 483 },
    { id: 'table-right-seat-3', table_id: 'table-right', x: 866, y: 548 },
    { id: 'table-right-seat-4', table_id: 'table-right', x: 833, y: 645 },
  ],
}

export const CAMERA_SCENES = {
  [STORE_ONE_SCENE.storeId]: STORE_ONE_SCENE,
  [STORE_TWO_SCENE.storeId]: STORE_TWO_SCENE,
}

export function getCameraScene(storeId) {
  return CAMERA_SCENES[storeId] ?? null
}
