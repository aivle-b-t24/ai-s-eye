const STORE_ONE_SCENE = {
  storeId: 'store-001',
  cameraId: 'store-001-cam1',
  label: 'CAM 01',
  objects: [
    {
      id: 'wall-back',
      type: 'wall',
      polygon: [[0, 0], [1000, 0], [1000, 430], [0, 430]],
    },
    {
      id: 'floor-main',
      type: 'floor',
      polygon: [[0, 400], [1000, 390], [1000, 1000], [0, 1000]],
    },
    {
      id: 'counter-main',
      type: 'counter',
      label: '카운터',
      polygon: [[555, 70], [1000, 80], [1000, 470], [770, 405], [580, 285]],
    },
    {
      id: 'wall-bench',
      type: 'wall',
      polygon: [[0, 365], [480, 245], [465, 455], [0, 660]],
    },
    {
      id: 'table-left',
      type: 'table',
      polygon: [[40, 545], [250, 495], [310, 640], [90, 725]],
    },
    {
      id: 'table-center-left',
      type: 'table',
      polygon: [[275, 420], [455, 380], [500, 500], [320, 555]],
    },
    {
      id: 'table-center',
      type: 'table',
      polygon: [[350, 590], [555, 545], [650, 690], [435, 780]],
    },
    {
      id: 'table-group',
      type: 'table',
      polygon: [[525, 330], [755, 330], [800, 485], [550, 500]],
    },
    {
      id: 'table-right',
      type: 'table',
      polygon: [[805, 425], [950, 430], [925, 610], [770, 570]],
    },
    {
      id: 'table-front',
      type: 'table',
      polygon: [[375, 750], [650, 685], [785, 880], [500, 1000], [330, 955]],
    },
    {
      id: 'counter-front-mask',
      type: 'occluder',
      polygon: [[580, 285], [770, 405], [1000, 470], [1000, 520], [760, 455], [565, 330]],
    },
    {
      id: 'table-left-front-mask',
      type: 'occluder',
      polygon: [[90, 680], [310, 600], [310, 640], [90, 725]],
    },
    {
      id: 'table-center-front-mask',
      type: 'occluder',
      polygon: [[435, 730], [650, 650], [650, 690], [435, 780]],
    },
    {
      id: 'table-front-mask',
      type: 'occluder',
      polygon: [[330, 900], [500, 945], [785, 830], [785, 880], [500, 1000], [330, 955]],
    },
  ],
}

const STORE_TWO_SCENE = {
  storeId: 'store-002',
  cameraId: 'store-002-cam1',
  label: 'CAM 02',
  objects: [
    {
      id: 'wall-back',
      type: 'wall',
      polygon: [[0, 0], [1000, 0], [1000, 390], [0, 390]],
    },
    {
      id: 'floor-main',
      type: 'floor',
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
      polygon: [[365, 405], [500, 405], [515, 520], [350, 525]],
    },
    {
      id: 'table-back-right',
      type: 'table',
      polygon: [[565, 385], [735, 385], [745, 500], [555, 505]],
    },
    {
      id: 'table-right',
      type: 'table',
      polygon: [[690, 465], [885, 455], [945, 610], [730, 635]],
    },
    {
      id: 'table-front',
      type: 'table',
      polygon: [[530, 590], [705, 540], [825, 860], [620, 990], [480, 865]],
    },
    {
      id: 'entrance-right',
      type: 'entrance',
      polygon: [[900, 250], [1000, 245], [1000, 520], [910, 505]],
    },
    {
      id: 'counter-front-mask',
      type: 'occluder',
      polygon: [[65, 680], [330, 545], [330, 600], [65, 735], [0, 655], [0, 610]],
    },
    {
      id: 'table-right-front-mask',
      type: 'occluder',
      polygon: [[730, 590], [945, 565], [945, 610], [730, 635]],
    },
    {
      id: 'table-front-mask',
      type: 'occluder',
      polygon: [[480, 820], [620, 940], [825, 810], [825, 860], [620, 990], [480, 865]],
    },
  ],
}

export const CAMERA_SCENES = {
  [STORE_ONE_SCENE.storeId]: STORE_ONE_SCENE,
  [STORE_TWO_SCENE.storeId]: STORE_TWO_SCENE,
}

export function getCameraScene(storeId) {
  return CAMERA_SCENES[storeId] ?? null
}
