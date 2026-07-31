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
      polygon: [[0, 365], [1000, 365], [1000, 1000], [0, 1000]],
    },
    {
      id: 'counter-main',
      type: 'counter',
      label: '카운터',
      polygon: [[0, 280], [285, 255], [330, 600], [65, 735], [0, 655]],
    },
    {
      id: 'entrance-center',
      type: 'entrance',
      label: '입구',
      polygon: [[255, 175], [400, 165], [410, 410], [270, 435]],
    },
    {
      id: 'wall-bench',
      type: 'wall',
      polygon: [[535, 310], [1000, 315], [1000, 565], [560, 545]],
    },
    {
      id: 'table-center',
      type: 'table',
      label: '테이블',
      polygon: [[365, 405], [500, 405], [515, 520], [350, 525]],
    },
    {
      id: 'table-back-right',
      type: 'table',
      label: '테이블',
      polygon: [[565, 385], [735, 385], [745, 500], [555, 505]],
    },
    {
      id: 'table-right',
      type: 'table',
      label: '테이블',
      polygon: [[690, 465], [885, 455], [945, 610], [730, 635]],
    },
    {
      id: 'table-front',
      type: 'table',
      label: '테이블',
      polygon: [[530, 590], [705, 540], [825, 860], [620, 990], [480, 865]],
    },
    {
      id: 'entrance-right',
      type: 'entrance',
      polygon: [[900, 250], [1000, 245], [1000, 520], [910, 505]],
    },
  ],
  seatAnchors: [
    { id: 'table-center-seat-1', table_id: 'table-center', x: 365, y: 575 },
    { id: 'table-center-seat-2', table_id: 'table-center', x: 495, y: 565 },
    { id: 'table-back-right-seat-1', table_id: 'table-back-right', x: 575, y: 535 },
    { id: 'table-back-right-seat-2', table_id: 'table-back-right', x: 720, y: 530 },
    { id: 'table-right-seat-1', table_id: 'table-right', x: 705, y: 675 },
    { id: 'table-right-seat-2', table_id: 'table-right', x: 880, y: 665 },
    { id: 'table-front-seat-1', table_id: 'table-front', x: 485, y: 735 },
    { id: 'table-front-seat-2', table_id: 'table-front', x: 555, y: 905 },
    { id: 'table-front-seat-3', table_id: 'table-front', x: 785, y: 690 },
    { id: 'table-front-seat-4', table_id: 'table-front', x: 835, y: 845 },
  ],
}

export const CAMERA_SCENES = {
  [STORE_ONE_SCENE.storeId]: STORE_ONE_SCENE,
  [STORE_TWO_SCENE.storeId]: STORE_TWO_SCENE,
}

export function getCameraScene(storeId) {
  return CAMERA_SCENES[storeId] ?? null
}
