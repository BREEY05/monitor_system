/* =============================================================================
 * 设备情况 · 数字孪生场景 v5（twin-scene 重写）
 * Three.js 车间场景 + /api/twin/overview 轮询 + 全部 DOM 渲染与交互
 * 契约：docs/twin-contract.md v5
 * ========================================================================== */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

/* ------------------------------ 通用工具 ------------------------------ */
const $ = (id) => document.getElementById(id);
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const pad2 = (value) => String(value).padStart(2, '0');

const SPACING_X = 4.2;
const SPACING_Z = 4.0;
const ORIGIN = new THREE.Vector3(0, 0, 0);
const DEFAULT_THRESHOLDS = { temperature: 31, humidity: 60, vibration: 0.5 };
const RISK_META = {
  NORMAL: { text: '正常', cls: 'risk-normal' },
  WATCH: { text: '关注', cls: 'risk-watch' },
  WARNING: { text: '预警', cls: 'risk-warning' },
  CRITICAL: { text: '严重', cls: 'risk-critical' },
};

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value === null || value === undefined ? '' : String(value);
}
function toggleHidden(id, hidden) {
  const el = $(id);
  if (el) el.classList.toggle('is-hidden', !!hidden);
}
function removeClasses(el, names) {
  if (el) names.forEach((name) => el.classList.remove(name));
}
function escapeHtml(value) {
  return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}
function on(id, event, handler, options) {
  const el = $(id);
  if (el) el.addEventListener(event, handler, options);
}
function setButtonLabel(button, text) {
  if (!button) return;
  const holder = button.querySelector('.tool-label, .btn-label, [data-label]');
  if (holder) { holder.textContent = text; return; }
  if (!button.querySelector('svg')) { button.textContent = text; return; }
  // 保留内联 SVG 图标，只替换文本节点
  Array.from(button.childNodes).forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) button.removeChild(node);
  });
  button.appendChild(document.createTextNode(text));
}
function formatNumber(value, digits = 1, fallback = '--') {
  if (value === null || value === undefined || value === '') return fallback;
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : fallback;
}
function clockText(value, fallback = '--:--:--') {
  if (!value) return fallback;
  const matched = String(value).match(/(\d{2}:\d{2}:\d{2})/);
  if (matched) return matched[1];
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) return pad2(date.getHours()) + ':' + pad2(date.getMinutes()) + ':' + pad2(date.getSeconds());
  return fallback;
}
function currentClock() {
  const now = new Date();
  return pad2(now.getHours()) + ':' + pad2(now.getMinutes()) + ':' + pad2(now.getSeconds());
}
function postToParent(payload) {
  if (window.parent === window) return;
  try { window.parent.postMessage(payload, location.origin); } catch (error) { /* 忽略 */ }
}

/* ------------------------------ 运行状态 ------------------------------ */
const state = {
  apiUrl: location.origin,
  apiEpoch: 0,
  configDevices: [],
  overview: null,
  devices: [],
  assets: [],
  alertItems: [],
  selectedId: null,
  mode: 'plant',
  labelsVisible: true,
  rotate: false,
  filter: 'all',
  query: '',
  hoveredId: null,
  failures: 0,
  signature: '',
  generation: 0,
  pollingInFlight: false,
  parentVisible: true,
  configured: false,
  sceneReady: false,
  initialFramed: false,
  viewTouched: false,
  plantFramedCount: 0,
};

/* 三维运行时 */
let scene3 = null;
let camera = null;
let renderer = null;
let controls = null;
let roomGroup = null;
let equipmentGroup = null;
let stagePlatform = null;
let webglAvailable = false;
const loader = new GLTFLoader();
const camTween = {
  active: false,
  fromPos: new THREE.Vector3(),
  toPos: new THREE.Vector3(),
  fromTarget: new THREE.Vector3(),
  toTarget: new THREE.Vector3(),
  started: 0,
  duration: 650,
};
let pollTimer = 0;
let toastTimer = 0;
let raycaster = null;
let pointerState = null;
let lastHoverAt = 0;

/* ------------------------------ 提示与状态 ------------------------------ */
function showToast(message, duration = 1800) {
  const el = $('stageToast');
  if (!el) return;
  el.textContent = String(message);
  el.classList.remove('is-hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('is-hidden'), duration);
}

function statusInfo(data) {
  const open = Number(data?.alerts?.open || 0);
  const online = data?.online;
  if (open > 0) return { kind: 'alarm', text: '告警 ' + open, tag: '告警', stateClass: 'state-danger' };
  if (online === false) return { kind: 'offline', text: '离线', tag: '离线', stateClass: 'state-offline' };
  if (online === undefined || online === null) return { kind: 'unknown', text: '无数据', tag: '无数据', stateClass: 'state-offline' };
  return { kind: 'running', text: '运行中', tag: '运行中', stateClass: 'state-normal' };
}
function isAlarm(asset) {
  return Number(asset?.data?.alerts?.open || 0) > 0;
}
function setStatusText(id, text, stateClass) {
  const el = $(id);
  if (!el) return;
  el.textContent = text;
  removeClasses(el, ['state-normal', 'state-offline', 'state-danger', 'state-warning', 'state-idle']);
  if (stateClass) el.classList.add(stateClass);
}
function setLivePill(data) {
  const pill = $('livePill');
  const textEl = $('livePillText');
  let cls = 'is-idle';
  let text = '暂无实时数据';
  if (state.failures > 0) {
    cls = 'is-error';
    text = '数据接口断开';
  } else if (data) {
    const source = data.source || {};
    const age = Number(source.age_seconds);
    const ageText = Number.isFinite(age) && age >= 0 ? Math.round(age) + 's' : '--';
    if (source.type === 'none') {
      cls = 'is-idle';
      text = '暂无实时数据';
    } else if (source.stale || source.online === false) {
      cls = 'is-stale';
      text = '已过期 ' + ageText;
    } else {
      cls = 'is-online';
      text = '实时 · ' + ageText;
    }
  }
  if (pill) {
    removeClasses(pill, ['is-online', 'is-stale', 'is-idle', 'is-error']);
    pill.classList.add(cls);
  }
  if (textEl) textEl.textContent = text;
}

/* ------------------------------ 设备数据合并 ------------------------------ */
function mergeDevices() {
  const map = new Map();
  const order = [];
  const ingest = (raw, fromOverview) => {
    if (!raw || raw.id === undefined || raw.id === null) return;
    const id = String(raw.id);
    if (!id) return;
    if (!map.has(id)) { map.set(id, { config: null, overview: null }); order.push(id); }
    const record = map.get(id);
    if (fromOverview) record.overview = raw;
    else record.config = raw;
  };
  state.configDevices.forEach((device) => ingest(device, false));
  (state.overview?.devices || []).forEach((device) => ingest(device, true));
  return order.map((id, index) => {
    const record = map.get(id);
    const config = record.config || {};
    const overview = record.overview || {};
    const modelUrl = overview.model_url || config.model_url || '';
    return {
      id,
      index: Number.isFinite(Number(overview.index)) ? Number(overview.index) : index,
      name: overview.name || config.name || '工业设备 #' + pad2(index + 1),
      station: overview.station || config.station || '工位 ' + pad2(index + 1),
      statusText: overview.status || config.status || '',
      online: typeof overview.online === 'boolean' ? overview.online : undefined,
      model_url: modelUrl,
      model_filename: overview.model_filename || config.model_filename || '',
      registered_at: config.registered_at || overview.registered_at || '',
      sensor_bound: !!overview.sensor_bound,
      risk: overview.risk || null,
      alerts: overview.alerts || { open: 0, latest_at: null },
      has_model: !!(overview.has_model || modelUrl),
    };
  });
}

function deviceById(id) {
  const key = String(id);
  return state.assets.find((asset) => asset.id === key) || null;
}
function selectedAsset() {
  return state.selectedId ? deviceById(state.selectedId) : null;
}

/* ------------------------------ 数据轮询 ------------------------------ */
function isPollingActive() {
  return state.parentVisible && !document.hidden;
}

function stopPolling() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = 0; }
}

function schedulePoll() {
  stopPolling();
  if (!isPollingActive()) return;
  const delay = state.failures > 0 ? 5000 : 3000;
  pollTimer = setTimeout(() => { pollTimer = 0; poll(false); }, delay);
}

async function fetchJson(path, timeout = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const url = /^https?:/i.test(path) ? path : state.apiUrl + path;
    const response = await fetch(url, { signal: controller.signal, cache: 'no-store' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function poll(manual = false) {
  if (!manual && !isPollingActive()) return;
  if (state.pollingInFlight) return;
  const epoch = state.apiEpoch;
  state.pollingInFlight = true;
  const refreshBtn = manual ? $('refreshBtn') : null;
  if (refreshBtn) refreshBtn.classList.add('is-loading');
  try {
    const data = await fetchJson('/api/twin/overview', 6000);
    if (epoch !== state.apiEpoch) return;
    state.failures = 0;
    applyOverview(data);
  } catch (error) {
    if (epoch !== state.apiEpoch) return;
    state.failures += 1;
    setLivePill(state.overview);
    if (manual || state.failures === 1) showToast('数据接口连接中断，正在重试…');
  } finally {
    state.pollingInFlight = false;
    if (refreshBtn) refreshBtn.classList.remove('is-loading');
    if (epoch === state.apiEpoch) schedulePoll();
  }
}

function applyOverview(data) {
  state.overview = data;
  syncDevices();
  renderUi();
  const updateEl = $('updateTime');
  if (updateEl) updateEl.textContent = '更新 ' + clockText(data?.generated_at, currentClock());
}

function syncDevices() {
  const devices = mergeDevices();
  state.devices = devices;
  const signature = JSON.stringify(devices.map((device) => [device.id, device.name, device.station, device.model_url, device.model_filename]));
  if (signature === state.signature && state.assets.length > 0) {
    state.assets.forEach((asset) => {
      const data = devices.find((device) => device.id === asset.id);
      if (data) asset.data = data;
    });
    updateAlarmState();
    return;
  }
  state.signature = signature;
  rebuildAssets(devices);
}

function updateAlarmState() {
  state.assets.forEach((asset) => { asset.alarm = isAlarm(asset); });
}

/* ------------------------------ 场景资源 ------------------------------ */
const sharedMaterials = new Set();
function material(color, roughness = 0.5, metalness = 0.3) {
  const mat = new THREE.MeshStandardMaterial({ color, roughness, metalness });
  sharedMaterials.add(mat);
  return mat;
}
function lineMaterial(color, opacity = 1) {
  const mat = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity });
  sharedMaterials.add(mat);
  return mat;
}
function basicMaterial(options) {
  const mat = new THREE.MeshBasicMaterial(options);
  sharedMaterials.add(mat);
  return mat;
}

const palette = [0x557f9b, 0x648c89, 0x8f9bae, 0x6f8caa];
const materials = {
  steel: material(0xbcc7cd, 0.36, 0.65),
  dark: material(0x415365, 0.48, 0.48),
  brass: material(0xb58d4d, 0.4, 0.55),
  white: material(0xe7ecf0, 0.65, 0.12),
  screen: material(0x223f56, 0.35, 0.3),
  black: material(0x26333e, 0.65, 0.2),
};
const roomMaterials = {
  floor: material(0xe7ecf3, 0.95, 0.02),
  plate: material(0xdde5ee, 0.92, 0.03),
  wall: material(0xdde5ee, 0.9, 0.02),
  column: material(0xc3cfdc, 0.75, 0.08),
  platform: material(0xd5dee9, 0.9, 0.04),
  marking: lineMaterial(0xc9a544),
  platformRing: basicMaterial({ color: 0x2f6fd0, transparent: true, opacity: 0.6, side: THREE.DoubleSide, depthWrite: false }),
  selectionRing: basicMaterial({ color: 0x2f6fd0, transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false }),
};

function box(parent, position, size, mat) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(size[0], size[1], size[2]), mat);
  mesh.position.set(position[0], position[1], position[2]);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}
function cylinder(parent, position, radius, height, mat, rotation = [0, 0, 0]) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, height, 24), mat);
  mesh.position.set(position[0], position[1], position[2]);
  mesh.rotation.set(rotation[0], rotation[1], rotation[2]);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}
function disposeObject(object) {
  if (!object) return;
  const geometries = new Set();
  const localMaterials = new Set();
  const textures = new Set();
  object.traverse((node) => {
    if (node.geometry) geometries.add(node.geometry);
    if (node.material) {
      const list = Array.isArray(node.material) ? node.material : [node.material];
      list.forEach((mat) => {
        if (!mat || sharedMaterials.has(mat)) return;
        localMaterials.add(mat);
        Object.values(mat).forEach((value) => {
          if (value && value.isTexture) textures.add(value);
        });
      });
    }
  });
  geometries.forEach((geometry) => geometry.dispose());
  textures.forEach((texture) => texture.dispose());
  localMaterials.forEach((mat) => mat.dispose());
  if (object.parent) object.parent.remove(object);
}
function clearGroup(group) {
  if (!group) return;
  group.children.slice().forEach((child) => disposeObject(child));
}

/* ------------------------------ 内置设备外形 ------------------------------ */
function typeFor(device) {
  const name = ((device.name || '') + ' ' + (device.model_filename || '')).toLowerCase();
  if (/泵|pump/.test(name)) return 'pump';
  if (/水箱|储罐|tank/.test(name)) return 'tank';
  if (/压缩|compress/.test(name)) return 'compressor';
  if (/控制|电气|传感|sensor|cabinet/.test(name)) return 'cabinet';
  if (/风机|fan/.test(name)) return 'fan';
  return 'engine';
}

function simplified(device, index) {
  const group = new THREE.Group();
  const shell = material(palette[index % palette.length], 0.44, 0.38);
  const { steel, dark, brass, white, screen, black } = materials;
  box(group, [0, 0.1, 0], [2.35, 0.2, 1.4], dark);
  for (const x of [-0.9, 0.9]) for (const z of [-0.48, 0.48]) cylinder(group, [x, 0.2, z], 0.09, 0.16, steel);
  switch (typeFor(device)) {
    case 'pump':
      cylinder(group, [-0.62, 0.66, 0], 0.36, 0.78, shell, [0, 0, Math.PI / 2]);
      for (let i = 0; i < 7; i += 1) cylinder(group, [-0.92 + i * 0.1, 0.66, 0], 0.39, 0.026, steel, [0, 0, Math.PI / 2]);
      cylinder(group, [0.3, 0.63, 0], 0.43, 0.55, shell, [Math.PI / 2, 0, 0]);
      cylinder(group, [0.3, 0.63, 0.36], 0.18, 0.25, steel, [Math.PI / 2, 0, 0]);
      cylinder(group, [0.45, 1.08, 0], 0.15, 0.4, steel);
      cylinder(group, [0.45, 1.3, 0], 0.22, 0.055, brass);
      box(group, [-0.62, 0.32, 0], [0.6, 0.25, 0.5], steel);
      break;
    case 'tank':
      cylinder(group, [0, 1.04, 0], 0.64, 1.6, shell);
      cylinder(group, [0, 1.88, 0], 0.65, 0.09, steel);
      cylinder(group, [0, 0.26, 0], 0.65, 0.08, steel);
      cylinder(group, [0, 2.03, 0], 0.12, 0.24, brass);
      box(group, [0.2, 1.08, 0.65], [0.065, 1.3, 0.04], steel);
      for (const y of [0.4, 1.72]) cylinder(group, [0.7, y, 0], 0.12, 0.37, brass, [0, 0, Math.PI / 2]);
      break;
    case 'cabinet':
      box(group, [0, 1.14, 0], [1.6, 1.94, 0.8], white);
      box(group, [0, 1.16, 0.42], [1.47, 1.8, 0.035], shell);
      box(group, [-0.18, 1.63, 0.45], [0.64, 0.42, 0.03], black);
      box(group, [-0.18, 1.63, 0.47], [0.54, 0.32, 0.02], screen);
      box(group, [0.51, 1.05, 0.47], [0.045, 0.37, 0.045], steel);
      for (let i = 0; i < 4; i += 1) cylinder(group, [-0.44 + i * 0.22, 1.18, 0.47], 0.045, 0.03, i === 3 ? brass : steel, [Math.PI / 2, 0, 0]);
      for (let i = 0; i < 6; i += 1) box(group, [-0.18, 0.48 + i * 0.055, 0.46], [0.68, 0.015, 0.015], dark);
      break;
    case 'compressor':
      cylinder(group, [0, 0.6, 0], 0.4, 1.7, shell, [0, 0, Math.PI / 2]);
      box(group, [-0.45, 1.14, 0], [0.7, 0.5, 0.65], dark);
      cylinder(group, [0.3, 1.12, 0], 0.28, 0.65, steel);
      cylinder(group, [0.75, 0.86, 0], 0.08, 0.6, brass);
      break;
    case 'fan':
      cylinder(group, [0, 1.02, 0], 0.72, 0.65, shell, [Math.PI / 2, 0, 0]);
      cylinder(group, [0, 1.02, 0.35], 0.14, 0.16, steel, [Math.PI / 2, 0, 0]);
      for (let i = 0; i < 6; i += 1) {
        const blade = box(group, [0, 1.02, 0.35], [0.12, 1.15, 0.06], steel);
        blade.rotation.z = (i * Math.PI) / 3;
      }
      box(group, [0, 0.38, 0], [1.3, 0.25, 0.8], dark);
      break;
    default:
      box(group, [-0.2, 0.78, 0], [1.2, 0.85, 0.92], shell);
      box(group, [-0.2, 1.28, 0], [1.34, 0.17, 1.02], dark);
      for (let i = 0; i < 4; i += 1) {
        box(group, [-0.66 + i * 0.31, 1.42, 0], [0.23, 0.16, 0.65], steel);
        cylinder(group, [-0.66 + i * 0.31, 1.49, 0.25], 0.04, 0.16, brass);
      }
      cylinder(group, [0.74, 0.77, 0], 0.42, 0.66, steel, [0, 0, Math.PI / 2]);
      box(group, [-0.87, 0.86, 0], [0.2, 1.05, 1.08], dark);
      for (let i = 0; i < 9; i += 1) box(group, [-0.99, 0.43 + i * 0.1, 0], [0.035, 0.025, 0.9], steel);
      cylinder(group, [0.14, 1.69, -0.3], 0.1, 0.54, dark);
      cylinder(group, [-0.2, 0.55, 0.54], 0.065, 0.9, brass, [0, 0, Math.PI / 2]);
  }
  return group;
}

function fitModel(model) {
  model.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(model);
  const size = bounds.getSize(new THREE.Vector3());
  if (![size.x, size.y, size.z].every(Number.isFinite) || size.length() < 0.00001) throw new Error('模型内容为空');
  const scale = Math.min(
    2.35 / Math.max(size.x, 0.001),
    2.1 / Math.max(size.y, 0.001),
    1.8 / Math.max(size.z, 0.001),
  );
  const normalizer = new THREE.Group();
  normalizer.add(model);
  normalizer.scale.setScalar(scale);
  normalizer.updateMatrixWorld(true);
  const scaled = new THREE.Box3().setFromObject(normalizer);
  const center = scaled.getCenter(new THREE.Vector3());
  normalizer.position.set(-center.x, -scaled.min.y + 0.02, -center.z);
  model.traverse((node) => {
    if (node.isMesh) { node.castShadow = true; node.receiveShadow = true; }
  });
  return normalizer;
}

/* ------------------------------ 设备装配 ------------------------------ */
function layoutPositions(list) {
  const count = Math.max(list.length, 1);
  const columns = Math.min(3, count);
  const rows = Math.max(1, Math.ceil(count / columns));
  return list.map((device, index) => {
    const row = Math.floor(index / columns);
    const column = index % columns;
    const rowCount = Math.min(columns, count - row * columns);
    const x = (column - (rowCount - 1) / 2) * SPACING_X;
    const z = -((row - (rows - 1) / 2) * SPACING_Z);
    return new THREE.Vector3(x, 0, z);
  });
}

function createSelectionRing() {
  const mesh = new THREE.Mesh(new THREE.RingGeometry(1.42, 1.62, 64), roomMaterials.selectionRing);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = 0.025;
  mesh.visible = false;
  mesh.renderOrder = 2;
  return mesh;
}

function createAsset(device, position, index, generation) {
  const asset = {
    id: device.id,
    data: device,
    index,
    source: device.model_url ? 'loading' : 'fallback',
    wrapper: null,
    content: null,
    ring: null,
    outline: null,
    label: null,
    basePosition: position.clone(),
    anchorY: 2.6,
    controller: null,
    alarm: false,
  };
  if (!scene3 || !equipmentGroup) {
    asset.source = 'fallback';
    return asset;
  }
  const wrapper = new THREE.Group();
  wrapper.position.copy(position);
  wrapper.userData.deviceId = device.id;
  const content = simplified(device, index);
  wrapper.add(content);
  const ring = createSelectionRing();
  wrapper.add(ring);
  const label = document.createElement('div');
  label.className = 'model-label';
  label.dataset.deviceId = device.id;
  label.textContent = (device.station || '') + ' · ' + (device.name || '');
  const labelHost = $('labels');
  if (labelHost) labelHost.appendChild(label);
  equipmentGroup.add(wrapper);
  asset.wrapper = wrapper;
  asset.content = content;
  asset.ring = ring;
  asset.label = label;
  measureAsset(asset);
  updateOutline(asset);
  asset.alarm = isAlarm(asset);
  if (device.model_url) loadModel(asset, generation);
  return asset;
}

function measureAsset(asset) {
  if (!asset.content) return;
  sizeAsset(asset);
  const box3 = new THREE.Box3().setFromObject(asset.content);
  if (box3.isEmpty()) return;
  const size = box3.getSize(new THREE.Vector3());
  asset.anchorY = Math.min(Math.max(box3.max.y + 0.45, 1.6), 4.2);
  const radius = Math.max(Math.max(size.x, size.z) / 2 + 0.25, 1.3);
  if (asset.ring) {
    asset.ring.geometry.dispose();
    asset.ring.geometry = new THREE.RingGeometry(radius * 0.9, radius, 64);
  }
}

function sizeAsset(asset) {
  // 世界矩阵必须先刷新：wrapper 刚创建/移动时 matrixWorld 仍是旧值，
  // 否则 Box3 会按局部坐标测量，outline 会被补偿成 -wrapper.position。
  if (asset?.wrapper) asset.wrapper.updateWorldMatrix(true, true);
}

function updateOutline(asset) {
  if (!asset.wrapper || !asset.content) return;
  if (asset.outline) { disposeObject(asset.outline); asset.outline = null; }
  sizeAsset(asset);
  const box3 = new THREE.Box3().setFromObject(asset.content);
  if (box3.isEmpty()) return;
  const size = box3.getSize(new THREE.Vector3());
  const center = box3.getCenter(new THREE.Vector3());
  asset.wrapper.worldToLocal(center);
  const outline = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(
      Math.max(size.x, 0.5) + 0.14,
      Math.max(size.y, 0.5) + 0.14,
      Math.max(size.z, 0.5) + 0.14,
    )),
    new THREE.LineBasicMaterial({ color: 0x2f6fd0, transparent: true, opacity: 0.3 }),
  );
  outline.position.copy(center);
  outline.visible = false;
  asset.outline = outline;
  asset.wrapper.add(outline);
}

function replaceAssetContent(asset, content) {
  if (!asset.wrapper || !content) return;
  if (asset.content) disposeObject(asset.content);
  asset.content = content;
  asset.wrapper.add(content);
  measureAsset(asset);
  updateOutline(asset);
}

async function loadModel(asset, generation) {
  if (!asset.data.model_url || !scene3) { asset.source = 'fallback'; return; }
  const controller = new AbortController();
  asset.controller = controller;
  const timer = setTimeout(() => controller.abort(), 15000);
  let parsed = null;
  let normalized = null;
  try {
    const url = new URL(asset.data.model_url, state.apiUrl + '/');
    if (!/^https?:$/.test(url.protocol)) throw new Error('不支持的模型地址');
    const response = await fetch(url.href, { signal: controller.signal, mode: 'cors', cache: 'no-store' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const buffer = await response.arrayBuffer();
    const result = await loader.parseAsync(buffer, new URL('.', url.href).href);
    parsed = result.scene;
    if (generation !== state.generation) { disposeObject(parsed); return; }
    normalized = fitModel(parsed);
    parsed = null;
    replaceAssetContent(asset, normalized);
    normalized = null;
    asset.source = 'configured';
  } catch (error) {
    if (generation !== state.generation) {
      if (parsed) disposeObject(parsed);
      return;
    }
    if (parsed) disposeObject(parsed);
    if (normalized) disposeObject(normalized);
    asset.source = 'fallback';
  } finally {
    clearTimeout(timer);
    if (asset.controller === controller) asset.controller = null;
    if (generation === state.generation) {
      updateCounts();
      renderAssembly();
      renderDetails();
      // GLB 就绪后按真实包围盒重新框选车间；用户已拖拽/聚焦则不打断其视角。
      if (asset.source === 'configured' && state.mode === 'plant' && !state.viewTouched) framePlant();
    }
  }
}

function rebuildAssets(devices) {
  const previousId = state.selectedId;
  state.generation += 1;
  const generation = state.generation;
  state.assets.forEach((asset) => {
    asset.controller?.abort();
    if (asset.label) asset.label.remove();
    if (asset.wrapper) disposeObject(asset.wrapper);
  });
  state.assets = [];
  const positions = layoutPositions(devices);
  devices.forEach((device, index) => {
    state.assets.push(createAsset(device, positions[index] || ORIGIN.clone(), index, generation));
  });
  if (scene3) {
    buildRoom();
    const target = previousId ? deviceById(previousId) : null;
    const fallback = target || state.assets[0] || null;
    state.selectedId = fallback ? fallback.id : null;
    if (state.mode === 'device' && !fallback) state.mode = 'plant';
    if (state.mode === 'device') applyDeviceLayout(); else applyPlantLayout();
    if (!state.initialFramed && state.assets.length) {
      // 首帧可能在设备配置尚未齐全时计算，后续 syncDevices 补齐设备时必须按完整包围盒重新取景。
      state.initialFramed = true;
      applyView(computeView(boundsOfVisible(), { kind: 'plant' }));
      state.plantFramedCount = state.assets.length;
    } else if (state.mode === 'plant' && state.assets.length && state.assets.length !== state.plantFramedCount && !state.viewTouched) {
      framePlant();
    }
  } else {
    state.selectedId = state.assets[0]?.id || null;
  }
  updateAlarmState();
  updateCounts();
  renderUi();
}

/* ------------------------------ 车间场景 ------------------------------ */
function buildRoom() {
  if (!roomGroup || !scene3) return;
  clearGroup(roomGroup);
  const count = Math.max(state.assets.length, 1);
  const columns = Math.min(3, count);
  const rows = Math.max(1, Math.ceil(count / columns));
  const width = columns * SPACING_X + 4.4;
  const halfDepth = ((rows - 1) * SPACING_Z) / 2 + 3.6;
  const depth = halfDepth * 2 + 3;
  const backZ = -halfDepth - 0.15;

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(width + 8, depth + 8), roomMaterials.floor);
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.02;
  floor.receiveShadow = true;
  roomGroup.add(floor);

  const gridSize = Math.ceil(Math.max(width, depth) + 8);
  const grid = new THREE.GridHelper(gridSize, Math.round(gridSize), 0xc3d1df, 0xd9e3ed);
  grid.position.y = 0;
  roomGroup.add(grid);

  const wall = box(roomGroup, [0, 1.65, backZ], [width + 2.4, 3.3, 0.18], roomMaterials.wall);
  wall.receiveShadow = true;
  box(roomGroup, [0, 0.18, backZ + 0.1], [width + 2.4, 0.36, 0.04], roomMaterials.column);
  box(roomGroup, [0, 3.3, backZ + 0.1], [width + 2.6, 0.16, 0.24], roomMaterials.column);
  for (const x of [-width / 2 - 0.5, -width / 6, width / 6, width / 2 + 0.5]) {
    box(roomGroup, [x, 1.75, backZ + 0.12], [0.16, 3.5, 0.22], roomMaterials.column);
  }

  state.assets.forEach((asset) => {
    const x = asset.basePosition.x;
    const z = asset.basePosition.z;
    const plate = new THREE.Mesh(new THREE.PlaneGeometry(3.5, 2.9), roomMaterials.plate);
    plate.rotation.x = -Math.PI / 2;
    plate.position.set(x, 0.001, z);
    plate.receiveShadow = true;
    roomGroup.add(plate);
    const points = [[-1.75, -1.45], [1.75, -1.45], [1.75, 1.45], [-1.75, 1.45]]
      .map(([px, pz]) => new THREE.Vector3(px, 0.014, pz));
    const outline = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(points), roomMaterials.marking);
    outline.position.set(x, 0, z);
    roomGroup.add(outline);
    roomGroup.add(makeGroundText(asset.data.station || '工位', x, z + 1.05));
  });
}

function makeGroundText(text, x, z) {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 128;
  const context = canvas.getContext('2d');
  if (context) {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = 'rgba(84, 106, 130, 0.82)';
    context.font = 'bold 44px "Segoe UI", "Microsoft YaHei", sans-serif';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(String(text), canvas.width / 2, canvas.height / 2);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const plane = new THREE.Mesh(
    new THREE.PlaneGeometry(1.7, 0.85),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false }),
  );
  plane.rotation.x = -Math.PI / 2;
  plane.position.set(x, 0.016, z);
  return plane;
}

function buildStagePlatform() {
  if (!stagePlatform || !scene3) return;
  clearGroup(stagePlatform);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(3.1, 3.25, 0.24, 56), roomMaterials.platform);
  base.position.y = -0.12;
  base.receiveShadow = true;
  base.castShadow = false;
  stagePlatform.add(base);
  const ring = new THREE.Mesh(new THREE.RingGeometry(2.58, 2.76, 64), roomMaterials.platformRing);
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.012;
  stagePlatform.add(ring);
  const grid = new THREE.GridHelper(6, 12, 0xc7d4e2, 0xdde6ef);
  grid.position.y = 0.006;
  stagePlatform.add(grid);
  stagePlatform.visible = false;
}

/* ------------------------------ 相机与视图 ------------------------------ */
function computeView(box3, options = {}) {
  const front = !!options.front;
  const kind = options.kind || 'plant';
  const center = box3.getCenter(new THREE.Vector3());
  const size = box3.getSize(new THREE.Vector3());
  const halfVertical = THREE.MathUtils.degToRad((camera?.fov || 38) / 2);
  const aspect = Math.max(camera?.aspect || 1.5, 0.4);
  const halfHorizontal = Math.atan(Math.tan(halfVertical) * aspect);
  const distanceVertical = (Math.max(size.y, 1) / 2 + 0.6) / Math.tan(halfVertical);
  const distanceHorizontal = (Math.max(size.x, 1) / 2 + 0.6) / Math.tan(halfHorizontal);
  const distance = Math.max(distanceVertical, distanceHorizontal, size.z * 0.9) * (kind === 'device' ? 1.3 : 1.16) + (kind === 'device' ? 1.5 : 2.2);
  const direction = front
    ? new THREE.Vector3(0, 0.04, 1)
    : (kind === 'device' ? new THREE.Vector3(0.72, 0.5, 1) : new THREE.Vector3(0.42, 0.5, 1));
  direction.normalize();
  const position = center.clone().addScaledVector(direction, distance);
  const target = new THREE.Vector3(center.x, Math.max(center.y * 0.9, 0.9), center.z);
  return { position, target };
}

function boundsOfVisible() {
  const box3 = new THREE.Box3();
  state.assets.forEach((asset) => {
    if (asset.wrapper && asset.wrapper.visible) box3.expandByObject(asset.wrapper);
  });
  if (box3.isEmpty()) box3.set(new THREE.Vector3(-2.4, 0, -2), new THREE.Vector3(2.4, 2.2, 2));
  return box3;
}

function applyView(view) {
  if (!camera || !controls) return;
  camTween.active = false;
  camera.position.copy(view.position);
  controls.target.copy(view.target);
  controls.update();
  resizeScene();
}

function tweenCamera(position, target, duration = 650) {
  if (!camera || !controls) return;
  camTween.fromPos.copy(camera.position);
  camTween.fromTarget.copy(controls.target);
  camTween.toPos.copy(position);
  camTween.toTarget.copy(target);
  camTween.started = performance.now();
  camTween.duration = duration;
  camTween.active = true;
}

function updateCameraTween(now) {
  if (!camTween.active || !camera || !controls) return;
  const progress = clamp((now - camTween.started) / camTween.duration, 0, 1);
  const eased = easeInOutCubic(progress);
  camera.position.lerpVectors(camTween.fromPos, camTween.toPos, eased);
  controls.target.lerpVectors(camTween.fromTarget, camTween.toTarget, eased);
  if (progress >= 1) camTween.active = false;
}

function focusAsset(asset, options = {}) {
  if (!asset || !asset.wrapper || !camera || !controls) return;
  state.viewTouched = true;
  asset.wrapper.updateMatrixWorld(true);
  const box3 = new THREE.Box3().setFromObject(asset.wrapper);
  const view = computeView(box3, { front: !!options.front, kind: 'device' });
  if (options.immediate) applyView(view);
  else tweenCamera(view.position, view.target);
}

function framePlant(options = {}) {
  if (!camera || !controls) return;
  state.viewTouched = false;
  state.plantFramedCount = state.assets.length;
  const view = computeView(boundsOfVisible(), { front: !!options.front, kind: 'plant' });
  if (options.immediate) applyView(view);
  else tweenCamera(view.position, view.target);
}

function setFrontActive(active) {
  const button = $('frontBtn');
  if (!button) return;
  button.classList.toggle('is-active', !!active);
  button.setAttribute('aria-pressed', String(!!active));
}

/* ------------------------------ 场景初始化 ------------------------------ */
function initScene() {
  const host = $('canvasWrap');
  if (!host) throw new Error('页面缺少三维画布容器');
  if (typeof window.WebGLRenderingContext === 'undefined' && typeof window.WebGL2RenderingContext === 'undefined') {
    throw new Error('当前浏览器不支持 WebGL');
  }
  scene3 = new THREE.Scene();
  scene3.background = new THREE.Color(0xeef2f8);
  camera = new THREE.PerspectiveCamera(38, 1, 0.1, 400);
  camera.position.set(0, 8.5, 15);
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const canvas = renderer.domElement;
  canvas.style.display = 'block';
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  canvas.setAttribute('aria-label', '设备三维视图');
  host.appendChild(canvas);

  controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minPolarAngle = 0.12;
  controls.maxPolarAngle = Math.PI / 2 - 0.02;
  controls.minDistance = 2.5;
  controls.maxDistance = 80;
  controls.autoRotateSpeed = 0.9;
  controls.target.set(0, 1.1, 0);
  controls.addEventListener('start', () => {
    camTween.active = false;
    state.viewTouched = true;
    setFrontActive(false);
  });

  roomGroup = new THREE.Group();
  equipmentGroup = new THREE.Group();
  stagePlatform = new THREE.Group();
  scene3.add(roomGroup, equipmentGroup, stagePlatform);

  const hemi = new THREE.HemisphereLight(0xffffff, 0xa9b8c9, 2.15);
  scene3.add(hemi);
  const sun = new THREE.DirectionalLight(0xffffff, 2.6);
  sun.position.set(6, 14, 10);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -26, right: 26, top: 26, bottom: -26 });
  sun.shadow.normalBias = 0.04;
  scene3.add(sun);
  const fill = new THREE.DirectionalLight(0xd9e6ff, 1.15);
  fill.position.set(-9, 7, -6);
  scene3.add(fill);

  buildStagePlatform();
  resizeScene();
  webglAvailable = true;
}

function resizeScene() {
  const host = $('canvasWrap');
  if (!host || !renderer || !camera) return;
  const width = Math.max(1, host.clientWidth);
  const height = Math.max(1, host.clientHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function handleSceneFailure(error) {
  const message = '三维场景初始化失败：' + (error?.message || '当前环境不支持 WebGL');
  const box3 = $('stageError');
  if (box3) {
    box3.classList.remove('is-hidden');
    setText('stageErrorText', message);
  }
  toggleHidden('stageLoading', true);
  showToast('三维场景初始化失败，已降级为数据视图');
}

function disposeSceneQuietly() {
  try { controls?.dispose(); } catch (error) { /* 忽略 */ }
  try {
    if (renderer) {
      renderer.dispose();
      renderer.domElement.remove();
    }
  } catch (error) { /* 忽略 */ }
  scene3 = null; camera = null; renderer = null; controls = null;
  roomGroup = null; equipmentGroup = null; stagePlatform = null;
  webglAvailable = false;
}

/* ------------------------------ 动画循环 ------------------------------ */
const tmpVec = new THREE.Vector3();
const tmpVec2 = new THREE.Vector3();

function markSceneReady() {
  if (state.sceneReady) return;
  state.sceneReady = true;
  const host = $('canvasWrap');
  if (host) host.dataset.sceneReady = '1';
  toggleHidden('stageLoading', true);
}

function updateOutlines(now) {
  const pulse = 0.32 + 0.36 * Math.abs(Math.sin(now / 320));
  state.assets.forEach((asset) => {
    const outline = asset.outline;
    if (!outline) return;
    const alarm = isAlarm(asset);
    outline.visible = alarm && !!asset.wrapper?.visible;
    if (!outline.visible) return;
    outline.material.color.setHex(0xd64545);
    outline.material.opacity = pulse;
  });
}

function updateSelectionRings(now) {
  state.assets.forEach((asset) => {
    const ring = asset.ring;
    if (!ring) return;
    ring.visible = asset.id === state.selectedId && !!asset.wrapper?.visible;
    if (ring.visible) ring.rotation.z = -now * 0.0004;
  });
}

function updateLabels() {
  const host = $('canvasWrap');
  if (!host || !camera) return;
  const width = host.clientWidth;
  const height = host.clientHeight;
  if (width < 2 || height < 2) return;
  state.assets.forEach((asset) => {
    const label = asset.label;
    if (!label) return;
    if (!asset.wrapper || !asset.wrapper.visible) { label.style.display = 'none'; return; }
    asset.wrapper.getWorldPosition(tmpVec);
    tmpVec.y += asset.anchorY;
    tmpVec2.copy(tmpVec).project(camera);
    const visible = tmpVec2.z > -1 && tmpVec2.z < 1 && Math.abs(tmpVec2.x) < 1.25 && Math.abs(tmpVec2.y) < 1.3;
    if (!visible) { label.style.display = 'none'; return; }
    label.style.display = '';
    label.style.left = ((tmpVec2.x + 1) * width) / 2 + 'px';
    label.style.top = ((1 - tmpVec2.y) * height) / 2 + 'px';
  });
}

function drawAxis() {
  const canvas = $('axisCanvas');
  if (!canvas || !camera) return;
  const context = canvas.getContext('2d');
  if (!context) return;
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  const inverse = camera.quaternion.clone().invert();
  const centerX = width / 2;
  const centerY = height * 0.48;
  const radius = Math.min(width, height) * 0.3;
  const directions = [
    { text: 'X', color: '#c35058', vector: new THREE.Vector3(1, 0, 0) },
    { text: 'Y', color: '#27896a', vector: new THREE.Vector3(0, 1, 0) },
    { text: 'Z', color: '#3974b5', vector: new THREE.Vector3(0, 0, 1) },
  ].map((item) => ({ ...item, vector: item.vector.applyQuaternion(inverse) }))
    .sort((a, b) => a.vector.z - b.vector.z);
  context.font = 'bold 17px Consolas, monospace';
  context.lineWidth = 3;
  directions.forEach((item) => {
    const x = centerX + item.vector.x * radius;
    const y = centerY - item.vector.y * radius;
    context.strokeStyle = item.color;
    context.fillStyle = item.color;
    context.beginPath();
    context.moveTo(centerX, centerY);
    context.lineTo(x, y);
    context.stroke();
    context.beginPath();
    context.arc(x, y, 4, 0, Math.PI * 2);
    context.fill();
    context.fillText(item.text, x + (item.vector.x < -0.1 ? -17 : 7), y + (item.vector.y > 0.1 ? -5 : 16));
  });
}

function animateScene(now) {
  const host = $('canvasWrap');
  if (!host || !renderer || !camera) return;
  markSceneReady();
  const width = host.clientWidth;
  const height = host.clientHeight;
  if (width < 2 || height < 2) return;
  const active = state.parentVisible && !document.hidden;
  if (active) {
    updateCameraTween(now);
    if (controls) controls.update();
  }
  updateOutlines(now);
  updateSelectionRings(now);
  updateLabels();
  renderer.render(scene3, camera);
  drawAxis();
}

function requestAnimationLoop() {
  if (!renderer || !scene3 || !camera) return;
  const loop = (now) => {
    requestAnimationFrame(loop);
    animateScene(now);
  };
  requestAnimationFrame(loop);
}

/* ------------------------------ 布局模式 ------------------------------ */
function applyPlantLayout() {
  if (roomGroup) roomGroup.visible = true;
  if (stagePlatform) stagePlatform.visible = false;
  state.assets.forEach((asset) => {
    if (!asset.wrapper) return;
    asset.wrapper.visible = true;
    asset.wrapper.position.copy(asset.basePosition);
  });
}

function applyDeviceLayout() {
  const target = selectedAsset();
  if (roomGroup) roomGroup.visible = false;
  if (stagePlatform) stagePlatform.visible = !!target;
  state.assets.forEach((asset) => {
    if (!asset.wrapper) return;
    const isTarget = !!target && asset.id === target.id;
    asset.wrapper.visible = isTarget;
    asset.wrapper.position.copy(isTarget ? ORIGIN : asset.basePosition);
  });
}

function updateModeChrome() {
  const asset = selectedAsset();
  const isPlant = state.mode === 'plant';
  setText('stageTitle', isPlant ? '车间总览' : (asset?.data.name || '单机查看'));
  setText('stageSubtitle', isPlant
    ? state.assets.length + ' 台设备 · 车间总览'
    : (asset?.data.station || '工位') + ' · 单机');
  const plantBtn = $('plantBtn');
  if (plantBtn) {
    plantBtn.classList.toggle('is-active', isPlant);
    plantBtn.setAttribute('aria-pressed', String(isPlant));
  }
  if (isPlant) setFrontActive(false);
}

function showPlant() {
  state.mode = 'plant';
  applyPlantLayout();
  setFrontActive(false);
  updateModeChrome();
  renderSelection();
  framePlant();
  hideTooltip();
  state.hoveredId = null;
  renderTree();
}

function enterDevice(asset) {
  const target = asset || selectedAsset();
  if (!target) { showToast('请先选择一台设备'); return; }
  state.mode = 'device';
  state.selectedId = target.id;
  applyDeviceLayout();
  updateModeChrome();
  renderSelection();
  focusAsset(target);
  postToParent({ type: 'equipment-select', deviceId: target.id });
}

/* ------------------------------ 选中与渲染 ------------------------------ */
function updateSelectionVisuals() {
  state.assets.forEach((asset) => {
    const selected = asset.id === state.selectedId;
    if (asset.ring) asset.ring.visible = selected && !!asset.wrapper?.visible;
    if (asset.label) {
      asset.label.classList.toggle('is-active', selected);
      asset.label.classList.toggle('is-alarm', isAlarm(asset));
    }
  });
}

function renderSelection() {
  renderTree();
  renderDetails();
  renderRisk();
  renderHud(state.overview);
  renderAssembly();
  updateSelectionVisuals();
  updateCounts();
}

function select(idOrAsset, options = {}) {
  const asset = typeof idOrAsset === 'string' ? deviceById(idOrAsset) : (idOrAsset || null);
  if (!asset) return;
  const changed = state.selectedId !== asset.id;
  state.selectedId = asset.id;
  if (state.mode === 'device') applyDeviceLayout();
  renderSelection();
  updateModeChrome();
  if (options.focus !== false) focusAsset(asset, { front: !!options.front });
  if (changed && !options.silent) postToParent({ type: 'equipment-select', deviceId: asset.id });
  const host = $('canvasWrap');
  if (host) host.dataset.selectedId = asset.id;
}

function cycleSelection(delta) {
  if (!state.assets.length) return;
  let index = state.assets.findIndex((asset) => asset.id === state.selectedId);
  if (index < 0) index = delta > 0 ? -1 : 0;
  index = (index + delta + state.assets.length) % state.assets.length;
  select(state.assets[index]);
}

function updateCounts() {
  const host = $('canvasWrap');
  const configured = state.assets.filter((asset) => asset.source === 'configured').length;
  if (host) {
    host.dataset.modelCount = String(state.assets.length);
    host.dataset.configuredCount = String(configured);
    host.dataset.selectedId = state.selectedId || '';
  }
  setText('assetCount', state.assets.length + ' 台');
}

function renderKpi(data) {
  const summary = data?.summary || {};
  const hasData = !!data;
  setText('kpiTotal', hasData ? (summary.total ?? 0) : '--');
  setText('kpiOnline', hasData ? (summary.online ?? 0) : '--');
  const alerting = Number(summary.alerting || 0);
  setText('kpiAlert', hasData ? alerting : '--');
  const alertValue = $('kpiAlert');
  if (alertValue) {
    const flag = hasData && alerting > 0;
    alertValue.classList.toggle('has-alert', flag);
    const item = alertValue.closest('.kpi-item, .kpi, .kpi-cell') || alertValue.parentElement;
    if (item) item.classList.toggle('has-alert', flag);
  }
  const plant = data?.plant || {};
  setText('kpiTemp', formatNumber(plant.temperature, 1));
  setText('kpiHumidity', formatNumber(plant.humidity, 1));
  setText('kpiVibration', formatNumber(plant.vibration, 2));
}

function renderTree() {
  const tree = $('tree');
  const empty = $('sidebarEmpty');
  const query = state.query;
  const items = state.assets.filter((asset) => {
    const data = asset.data;
    const haystack = (data.name + ' ' + data.id + ' ' + data.station).toLowerCase();
    if (query && !haystack.includes(query)) return false;
    const kind = statusInfo(data).kind;
    if (state.filter === 'running') return kind === 'running';
    if (state.filter === 'alert') return kind === 'alarm';
    if (state.filter === 'offline') return kind === 'offline' || kind === 'unknown';
    return true;
  });
  if (tree) tree.innerHTML = items.map(deviceItemHtml).join('');
  if (empty) {
    empty.textContent = state.assets.length ? '没有匹配的设备' : '暂无设备配置，请检查设备设置';
    empty.classList.toggle('is-hidden', items.length > 0);
  }
  updateCounts();
}

function deviceItemHtml(asset) {
  const data = asset.data;
  const status = statusInfo(data);
  const open = Number(data?.alerts?.open || 0);
  const alarm = status.kind === 'alarm';
  const offline = status.kind === 'offline';
  const unknown = status.kind === 'unknown';
  const classes = ['device-item'];
  if (asset.id === state.selectedId) classes.push('is-active');
  if (alarm) classes.push('is-alarm');
  if (offline) classes.push('is-offline');
  if (unknown) classes.push('is-dim');
  if (asset.id === state.hoveredId) classes.push('is-hover');
  const tagClass = alarm ? 'alarm' : offline ? 'offline' : unknown ? 'muted' : 'running';
  const tags = ['<span class="tag tag-' + tagClass + '">' + escapeHtml(status.tag) + '</span>'];
  if (data.has_model) tags.push('<span class="tag tag-model">模型</span>');
  const badge = open > 0 ? '<span class="device-alarm-badge">' + open + '</span>' : '';
  return '<button type="button" class="' + classes.join(' ') + '" data-device-id="' + escapeHtml(asset.id) + '">'
    + '<span class="device-item-head"><span class="device-dot"></span><span class="device-name">' + escapeHtml(data.name) + '</span>' + badge + '</span>'
    + '<span class="device-meta">' + escapeHtml(data.station) + ' · ' + escapeHtml(asset.id) + '</span>'
    + '<span class="device-tags">' + tags.join('') + '</span>'
    + '</button>';
}

function renderDetails() {
  const asset = selectedAsset();
  const openButton = $('openDevice');
  if (!asset) {
    setText('partName', '未选择设备');
    setText('partIndex', '--');
    setText('partCode', '--');
    setText('stationName', '--');
    setText('modelFile', '--');
    setText('partSource', '--');
    setText('partRegistered', '—');
    setStatusText('partStatus', '暂无数据', 'state-idle');
    if (openButton) openButton.disabled = true;
    return;
  }
  if (openButton) openButton.disabled = false;
  const info = asset.data;
  const index = state.assets.indexOf(asset);
  const status = statusInfo(info);
  setText('partName', info.name);
  setText('partIndex', (index + 1) + '/' + state.assets.length);
  setText('partCode', info.id);
  setText('stationName', info.station || '—');
  setText('modelFile', info.model_filename || '未配置');
  setText('partSource', info.sensor_bound ? '设备直连传感' : (state.overview?.plant?.available ? '车间共享传感' : '暂无数据'));
  setText('partRegistered', info.registered_at || '—');
  setStatusText('partStatus', status.text, status.stateClass);
}

function setMetricValue(id, value, digits) {
  const number = Number(value);
  setText(id, value === null || value === undefined || !Number.isFinite(number) ? '--' : number.toFixed(digits));
}

function applyMetric(name, value, threshold, status, digits) {
  setMetricValue('metric' + name + 'Value', value, digits);
  const note = $('metric' + name + 'Note');
  if (note) {
    const thresholdNumber = Number(threshold);
    note.textContent = Number.isFinite(thresholdNumber)
      ? '阈值 ' + thresholdNumber.toFixed(thresholdNumber < 1 ? 2 : 1)
      : '阈值 --';
  }
  const bar = $('metric' + name + 'Bar');
  if (!bar) return;
  const numeric = Number(value);
  const limit = Number(threshold);
  const percent = Number.isFinite(numeric) && Number.isFinite(limit) && limit > 0
    ? clamp((numeric / limit) * 100, 0, 100)
    : 0;
  bar.style.width = percent.toFixed(1) + '%';
  removeClasses(bar, ['normal', 'warning', 'danger', 'missing', 'status-normal', 'status-warning', 'status-danger', 'status-missing', 'is-normal', 'is-warning', 'is-danger', 'is-missing']);
  const barStatus = ['normal', 'warning', 'danger'].includes(status)
    ? status
    : (Number.isFinite(numeric) ? 'normal' : 'missing');
  bar.classList.add('is-' + barStatus);
  bar.dataset.status = barStatus;
}

function renderMetrics(data) {
  const plant = data?.plant;
  const available = !!plant?.available;
  toggleHidden('sensorMetrics', !available);
  toggleHidden('sensorEmpty', available);
  const badge = $('sensorBadge');
  if (badge) {
    let text = '暂无数据';
    let cls = 'is-muted';
    if (available) {
      const stale = !!data?.source?.stale;
      if (stale) {
        text = '已过期';
        cls = 'is-warn';
      } else {
        text = '实时';
        const statuses = [plant?.statuses?.temperature, plant?.statuses?.humidity, plant?.statuses?.vibration];
        cls = statuses.includes('danger') ? 'is-alert' : (statuses.includes('warning') ? 'is-warn' : 'is-ok');
      }
    }
    badge.textContent = text;
    removeClasses(badge, ['is-live', 'is-warn', 'is-muted', 'is-ok', 'is-alert']);
    if (cls) badge.classList.add(cls);
  }
  setText('sensorUpdated', available ? '更新于 ' + clockText(plant.timestamp) : '更新于 --');
  if (!available) {
    ['Temp', 'Humidity', 'Vibration'].forEach((name) => applyMetric(name, null, null, 'missing', 1));
    return;
  }
  const thresholds = data.thresholds || DEFAULT_THRESHOLDS;
  applyMetric('Temp', plant.temperature, thresholds.temperature, plant.statuses?.temperature, 1);
  applyMetric('Humidity', plant.humidity, thresholds.humidity, plant.statuses?.humidity, 1);
  applyMetric('Vibration', plant.vibration, thresholds.vibration, plant.statuses?.vibration, 2);
}

function renderRisk() {
  const asset = selectedAsset();
  const risk = asset?.data?.risk;
  const badge = $('riskBadge');
  const reasons = $('riskReasons');
  const note = $('riskNote');
  const riskClasses = Object.values(RISK_META).map((meta) => meta.cls);
  const riskCard = $('riskCard');
  removeClasses(badge, riskClasses);
  removeClasses(riskCard, riskClasses);
  if (!risk) {
    if (badge) badge.textContent = '暂无数据';
    setText('riskScore', '--');
    if (reasons) reasons.innerHTML = '<li>暂无风险说明</li>';
    if (note) note.textContent = '暂无实时数据，仅基于近期告警';
    return;
  }
  const meta = RISK_META[risk.risk_level] || RISK_META.NORMAL;
  if (riskCard) riskCard.classList.add(meta.cls);
  if (badge) {
    badge.classList.add(meta.cls);
    badge.textContent = meta.text;
  }
  setText('riskScore', formatNumber(risk.risk_score, 1));
  if (reasons) {
    const list = Array.isArray(risk.reasons) ? risk.reasons.filter(Boolean) : [];
    const rows = list.length ? list : ['暂无风险说明'];
    reasons.innerHTML = rows.map((item) => '<li>' + escapeHtml(item) + '</li>').join('');
  }
  if (note) {
    note.textContent = risk.data_scope === 'device'
      ? '基于设备直连实时数据与近期告警'
      : risk.data_scope === 'plant'
        ? '基于车间共享传感与近期告警'
        : '暂无实时数据，仅基于近期告警';
  }
}

function renderAlerts(data) {
  const alerts = data?.alerts;
  const openTotal = Number(alerts?.open_total || 0);
  setText('alertCount', data ? '未处理 ' + openTotal : '未处理 --');
  const list = $('alertList');
  const items = Array.isArray(alerts?.items) ? alerts.items.slice(0, 5) : [];
  state.alertItems = items;
  if (list) {
    list.innerHTML = items.map((item, index) => {
      const level = String(item.level || 'info').toLowerCase();
      const levelClass = ['critical', 'danger', 'warning', 'high', 'info'].includes(level)
        ? 'is-' + (level === 'high' ? 'warning' : level)
        : 'is-info';
      const metaParts = [item.source, item.area, item.device_id].filter(Boolean)
        .filter((value, position, array) => array.indexOf(value) === position);
      const meta = metaParts.slice(0, 2).join(' · ') || '车间';
      return '<li class="alert-item ' + levelClass + '" role="button" tabindex="0" data-alert-index="' + index + '">'
        + '<span class="alert-item-head"><span class="alert-title">' + escapeHtml(item.title || '设备告警') + '</span>'
        + '<time class="alert-time">' + escapeHtml(clockText(item.time)) + '</time></span>'
        + '<span class="alert-meta">' + escapeHtml(meta) + '</span>'
        + '</li>';
    }).join('');
  }
  toggleHidden('alertEmpty', items.length > 0);
}

function renderHud(data) {
  const hud = $('stageHud');
  if (!hud) return;
  const asset = selectedAsset();
  if (!asset) { hud.classList.add('is-hidden'); return; }
  hud.classList.remove('is-hidden');
  const status = statusInfo(asset.data);
  const statusEl = $('hudStatus');
  if (statusEl) {
    statusEl.textContent = status.text;
    removeClasses(statusEl, ['state-normal', 'state-offline', 'state-danger', 'state-warning', 'is-alarm']);
    statusEl.classList.add(status.stateClass);
    if (status.kind === 'alarm') statusEl.classList.add('is-alarm');
  }
  setText('hudName', asset.data.name);
  setText('hudMeta', (asset.data.station || '—') + ' · ' + (asset.data.model_filename || (asset.source === 'configured' ? '配置模型' : '内置外形')));
  const plant = data?.plant;
  const available = !!plant?.available;
  setText('hudTemp', available ? formatNumber(plant.temperature, 1) : '--');
  setText('hudHumidity', available ? formatNumber(plant.humidity, 1) : '--');
  setText('hudVibration', available ? formatNumber(plant.vibration, 2) : '--');
}

function renderAssembly() {
  const total = state.assets.length;
  const configured = state.assets.filter((asset) => asset.source === 'configured').length;
  const fallback = state.assets.filter((asset) => asset.source === 'fallback').length;
  const loading = state.assets.filter((asset) => asset.source === 'loading').length;
  setText('assemblyInfo', total + ' 个工位 · ' + configured + ' 台配置模型 · ' + fallback + ' 台回退外形'
    + (loading ? '（' + loading + ' 台加载中）' : ''));
  const asset = selectedAsset();
  const note = $('modelNote');
  if (!note) return;
  if (!asset) { note.textContent = '选择设备后查看模型来源'; return; }
  const sourceText = asset.source === 'configured'
    ? '配置模型'
    : asset.source === 'loading'
      ? '内置外形（配置模型加载中）'
      : asset.data.model_url
        ? '内置外形（配置模型不可用）'
        : '内置外形（未配置模型）';
  note.textContent = (asset.data.model_filename || '未命名模型') + ' · ' + sourceText;
}

function renderUi() {
  renderKpi(state.overview);
  setLivePill(state.overview);
  renderTree();
  renderDetails();
  renderMetrics(state.overview);
  renderRisk();
  renderAlerts(state.overview);
  renderHud(state.overview);
  renderAssembly();
  updateCounts();
  updateSelectionVisuals();
  updateModeChrome();
  if (!state.selectedId && state.assets.length) {
    state.selectedId = state.assets[0].id;
    renderDetails();
    renderRisk();
    renderHud(state.overview);
    renderAssembly();
    updateSelectionVisuals();
    updateCounts();
  }
}

/* ------------------------------ 拾取与悬浮 ------------------------------ */
function pick(event) {
  if (!renderer || !camera || !raycaster) return null;
  const canvas = renderer.domElement;
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  const y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(new THREE.Vector2(x, y), camera);
  const targets = state.assets
    .map((asset) => asset.wrapper)
    .filter((wrapper) => wrapper && wrapper.visible);
  const hits = raycaster.intersectObjects(targets, true);
  for (const hit of hits) {
    let object = hit.object;
    while (object && !object.userData.deviceId) object = object.parent;
    const asset = object?.userData.deviceId ? deviceById(object.userData.deviceId) : null;
    if (asset) return asset;
  }
  return null;
}

function setHovered(id) {
  if (state.hoveredId === id) return;
  state.hoveredId = id;
  const tree = $('tree');
  if (!tree) return;
  tree.querySelectorAll('.device-item.is-hover').forEach((item) => item.classList.remove('is-hover'));
  if (id) {
    const target = Array.from(tree.querySelectorAll('.device-item'))
      .find((item) => item.dataset.deviceId === id);
    if (target) target.classList.add('is-hover');
  }
}

function hideTooltip() {
  const tip = $('deviceTip');
  if (tip) tip.classList.add('is-hidden');
  if (renderer) renderer.domElement.style.cursor = '';
  setHovered(null);
}

function showTooltip(asset, event) {
  const tip = $('deviceTip');
  if (!tip) return;
  setText('tipName', asset.data.name);
  setText('tipMeta', (asset.data.station || '—') + ' · ' + statusInfo(asset.data).tag);
  const stage = $('stage');
  const rect = (stage || $('canvasWrap'))?.getBoundingClientRect();
  if (!rect) return;
  tip.classList.remove('is-hidden');
  const left = event.clientX - rect.left + 16;
  const top = event.clientY - rect.top + 18;
  const maxLeft = Math.max(8, rect.width - (tip.offsetWidth || 160) - 8);
  const maxTop = Math.max(8, rect.height - (tip.offsetHeight || 54) - 8);
  tip.style.left = clamp(left, 8, maxLeft) + 'px';
  tip.style.top = clamp(top, 8, maxTop) + 'px';
  if (renderer) renderer.domElement.style.cursor = 'pointer';
  setHovered(asset.id);
}

/* ------------------------------ 视图操作 ------------------------------ */
function toggleLabels(force) {
  state.labelsVisible = typeof force === 'boolean' ? force : !state.labelsVisible;
  toggleHidden('labels', !state.labelsVisible);
  const button = $('labelsBtn');
  if (button) {
    button.classList.toggle('is-active', state.labelsVisible);
    button.setAttribute('aria-pressed', String(state.labelsVisible));
  }
}

function toggleRotate(force) {
  state.rotate = typeof force === 'boolean' ? force : !state.rotate;
  if (controls) controls.autoRotate = state.rotate;
  const button = $('rotateBtn');
  if (button) {
    button.classList.toggle('is-active', state.rotate);
    button.setAttribute('aria-pressed', String(state.rotate));
  }
}

function frontView() {
  const asset = selectedAsset();
  if (state.mode === 'device' && asset) focusAsset(asset, { front: true });
  else framePlant({ front: true });
  setFrontActive(true);
}

function resetView() {
  setFrontActive(false);
  if (state.mode === 'device') {
    const asset = selectedAsset();
    if (asset) focusAsset(asset);
    else showPlant();
  } else {
    framePlant();
  }
}

function syncFullscreenUi() {
  const button = $('fullscreenBtn');
  const stage = $('stage');
  const active = !!stage && document.fullscreenElement === stage;
  if (button) {
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', String(active));
    setButtonLabel(button, active ? '退出全屏' : '全屏');
  }
}

function toggleFullscreen() {
  const stage = $('stage');
  if (!stage) return;
  if (typeof document.fullscreenEnabled === 'boolean' && !document.fullscreenEnabled) {
    showToast('当前浏览器不支持全屏');
    return;
  }
  if (document.fullscreenElement) {
    document.exitFullscreen?.().catch(() => showToast('退出全屏失败'));
  } else if (stage.requestFullscreen) {
    stage.requestFullscreen().catch(() => showToast('当前浏览器不支持全屏'));
  } else {
    showToast('当前浏览器不支持全屏');
  }
}

function takeSnapshot() {
  if (!renderer || !scene3 || !camera) { showToast('三维场景尚未就绪'); return; }
  const host = $('canvasWrap');
  if (!host || host.clientWidth < 2) { showToast('三维场景尚未就绪'); return; }
  try {
    renderer.render(scene3, camera);
    const dataUrl = renderer.domElement.toDataURL('image/png');
    const now = new Date();
    const filename = 'twin-' + now.getFullYear() + pad2(now.getMonth() + 1) + pad2(now.getDate())
      + '-' + pad2(now.getHours()) + pad2(now.getMinutes()) + pad2(now.getSeconds()) + '.png';
    const link = document.createElement('a');
    link.href = dataUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    showToast('截图已保存');
  } catch (error) {
    showToast('截图失败，请重试');
  }
}

/* ------------------------------ 过滤器 ------------------------------ */
const FILTERS = [
  ['filterAll', 'all'],
  ['filterRunning', 'running'],
  ['filterAlert', 'alert'],
  ['filterOffline', 'offline'],
];

function setFilter(mode) {
  state.filter = mode;
  FILTERS.forEach(([id, value]) => {
    const button = $(id);
    if (!button) return;
    const active = value === mode;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  renderTree();
}

/* ------------------------------ 事件绑定 ------------------------------ */
function activateAlertItem(item) {
  const alert = state.alertItems[Number(item.dataset.alertIndex)];
  if (!alert) return;
  const deviceId = alert.device_id ? String(alert.device_id) : '';
  const asset = deviceId ? deviceById(deviceId) : null;
  if (asset) select(asset);
  else showToast('该告警来自未配置的传感设备');
}

function bindUi() {
  on('refreshBtn', 'click', () => { poll(true); });
  on('plantBtn', 'click', () => showPlant());
  on('frontBtn', 'click', () => frontView());
  on('labelsBtn', 'click', () => toggleLabels());
  on('rotateBtn', 'click', () => toggleRotate());
  on('fullscreenBtn', 'click', () => toggleFullscreen());
  on('snapshotBtn', 'click', () => takeSnapshot());
  on('resetBtn', 'click', () => resetView());
  on('openDevice', 'click', () => { if (state.selectedId) enterDevice(selectedAsset()); else showToast('请先选择设备'); });
  on('hudOpen', 'click', () => { if (state.selectedId) enterDevice(selectedAsset()); else showToast('请先选择设备'); });
  on('openSettings', 'click', () => {
    const asset = selectedAsset();
    if (!asset) { showToast('请先选择设备'); return; }
    if (window.parent === window) { showToast('请在主界面中打开设备设置'); return; }
    postToParent({ type: 'equipment-settings', deviceId: asset.id });
  });
  on('alertMore', 'click', () => {
    if (window.parent === window) { showToast('请在主界面查看全部告警'); return; }
    postToParent({ type: 'equipment-alerts' });
  });
  FILTERS.forEach(([id, value]) => on(id, 'click', () => setFilter(value)));
  on('search', 'input', (event) => {
    state.query = String(event.target.value || '').trim().toLowerCase();
    renderTree();
  });
  on('tree', 'click', (event) => {
    const button = event.target?.closest?.('.device-item');
    if (!button) return;
    const asset = deviceById(button.dataset.deviceId);
    if (!asset) return;
    // 列表项在选中后会被重新渲染，原生 dblclick 无法跨节点触发，用 click 的 detail 判定双击
    if (event.detail >= 2) { enterDevice(asset); return; }
    select(asset);
  });
  on('tree', 'dblclick', (event) => {
    const button = event.target?.closest?.('.device-item');
    if (!button) return;
    const asset = deviceById(button.dataset.deviceId);
    if (asset) enterDevice(asset);
  });
  on('labels', 'click', (event) => {
    const label = event.target?.closest?.('.model-label');
    if (!label) return;
    const asset = deviceById(label.dataset.deviceId);
    if (asset) select(asset);
  });
  on('alertList', 'click', (event) => {
    const item = event.target?.closest?.('.alert-item');
    if (item) activateAlertItem(item);
  });
  on('alertList', 'keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const item = event.target?.closest?.('.alert-item');
    if (!item) return;
    event.preventDefault();
    activateAlertItem(item);
  });
  const hudOpen = $('hudOpen');
  if (hudOpen) hudOpen.setAttribute('type', 'button');
  syncFullscreenUi();
  toggleLabels(state.labelsVisible);
  toggleRotate(state.rotate);
  setFilter(state.filter);
}

function bindSceneInteractions() {
  if (!renderer) return;
  const canvas = renderer.domElement;
  raycaster = new THREE.Raycaster();
  canvas.addEventListener('pointerdown', (event) => {
    pointerState = { x: event.clientX, y: event.clientY, dragging: false };
  });
  canvas.addEventListener('pointerup', (event) => {
    if (!pointerState) return;
    pointerState.dragging = Math.hypot(event.clientX - pointerState.x, event.clientY - pointerState.y) >= 6;
  });
  canvas.addEventListener('pointercancel', () => { pointerState = null; hideTooltip(); });
  canvas.addEventListener('pointermove', (event) => {
    if (pointerState && Math.hypot(event.clientX - pointerState.x, event.clientY - pointerState.y) >= 6) {
      pointerState.dragging = true;
    }
    if (pointerState?.dragging) { hideTooltip(); return; }
    const now = performance.now();
    if (now - lastHoverAt < 80) return;
    lastHoverAt = now;
    const asset = pick(event);
    if (asset) showTooltip(asset, event);
    else hideTooltip();
  });
  canvas.addEventListener('pointerleave', () => { pointerState = null; hideTooltip(); });
  canvas.addEventListener('click', (event) => {
    const reference = pointerState;
    pointerState = null;
    if (reference?.dragging) return;
    const asset = pick(event);
    if (asset) select(asset);
  });
  canvas.addEventListener('dblclick', (event) => {
    const asset = pick(event);
    if (asset) { select(asset); enterDevice(asset); }
  });
}

function bindKeyboard() {
  window.addEventListener('keydown', (event) => {
    const target = event.target;
    const tag = String(target?.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || target?.isContentEditable) return;
    switch (event.key) {
      case 'Escape':
        if (state.mode === 'device') { event.preventDefault(); showPlant(); }
        break;
      case 'Enter':
        if (state.selectedId) { event.preventDefault(); enterDevice(selectedAsset()); }
        break;
      case 'r':
      case 'R':
        resetView();
        break;
      case 'f':
      case 'F':
        frontView();
        break;
      case 'l':
      case 'L':
        toggleLabels();
        break;
      case ' ':
        event.preventDefault();
        toggleRotate();
        break;
      case 'ArrowUp':
        event.preventDefault();
        cycleSelection(-1);
        break;
      case 'ArrowDown':
        event.preventDefault();
        cycleSelection(1);
        break;
      default:
        break;
    }
  });
}

function bindVisibility() {
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopPolling();
    else poll(true);
  });
  document.addEventListener('fullscreenchange', syncFullscreenUi);
}

function bindMessages() {
  window.addEventListener('message', (event) => {
    if (window.parent === window || event.source !== window.parent) return;
    if (event.origin !== location.origin) return;
    const data = event.data;
    if (!data || typeof data !== 'object') return;
    if (data.type === 'monitor-config') handleMonitorConfig(data);
    else if (data.type === 'equipment-visibility') setParentVisible(data.visible !== false);
  });
}

function handleMonitorConfig(data) {
  state.configured = true;
  const nextApi = typeof data.apiUrl === 'string' && data.apiUrl.trim()
    ? data.apiUrl.trim().replace(/\/+$/, '')
    : '';
  if (nextApi && nextApi !== state.apiUrl) {
    state.apiUrl = nextApi;
    state.apiEpoch += 1;
  }
  if (Array.isArray(data.devices)) state.configDevices = data.devices;
  syncDevices();
  renderUi();
  state.failures = 0;
  poll(true);
}

function setParentVisible(visible) {
  state.parentVisible = visible !== false;
  if (!state.parentVisible) {
    stopPolling();
    hideTooltip();
  } else {
    poll(true);
  }
}

async function loadSettingsFallback() {
  if (state.configured) return;
  try {
    const settings = await fetchJson('/api/settings', 8000);
    if (state.configured) return;
    if (Array.isArray(settings?.devices) && settings.devices.length) {
      state.configDevices = settings.devices;
      syncDevices();
      renderUi();
    }
  } catch (error) {
    setText('assemblyInfo', '设备配置读取失败，请检查本地服务');
  }
}

function observeResize() {
  const host = $('canvasWrap');
  if (!host) return;
  resizeScene();
  if (typeof ResizeObserver !== 'undefined') {
    const observer = new ResizeObserver(() => resizeScene());
    observer.observe(host);
  }
  window.addEventListener('resize', () => resizeScene());
}

/* ------------------------------ 启动 ------------------------------ */
function bootstrap() {
  try {
    initScene();
    bindSceneInteractions();
  } catch (error) {
    disposeSceneQuietly();
    handleSceneFailure(error);
  }
  bindUi();
  bindKeyboard();
  bindVisibility();
  bindMessages();
  observeResize();
  updateModeChrome();
  requestAnimationLoop();
  postToParent({ type: 'equipment-ready' });
  poll(true);
  setTimeout(loadSettingsFallback, 400);
  setTimeout(() => {
    if (!state.sceneReady && webglAvailable) markSceneReady();
  }, 6000);
}

bootstrap();
