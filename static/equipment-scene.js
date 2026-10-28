import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const $ = id => document.getElementById(id);
const host = $('canvasWrap');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf0f4f8);
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
host.appendChild(renderer.domElement);
const camera = new THREE.PerspectiveCamera(36, 1, .1, 250);
camera.up.set(0, 1, 0);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = .1;
controls.minPolarAngle = .2;
controls.maxPolarAngle = Math.PI / 2;
controls.minDistance = 2;
controls.maxDistance = 70;
const equipment = new THREE.Group();
const room = new THREE.Group();
scene.add(room, equipment, new THREE.HemisphereLight(0xffffff, 0x9caec2, 2.1));
const sun = new THREE.DirectionalLight(0xffffff, 3);
sun.position.set(4, 12, 8);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -18, right: 18, top: 18, bottom: -18 });
sun.shadow.normalBias = .035;
scene.add(sun);
const fill = new THREE.DirectionalLight(0xd6e5ff, 1.4);
fill.position.set(-8, 6, -3);
scene.add(fill);

let assets = [], selected = null, mode = 'plant', generation = 0;
let apiUrl = location.origin, labelsVisible = true, signature = '';
let alertIds = new Set(), alertServiceAvailable = false;
const loader = new GLTFLoader();
const palette = [0x557f9b, 0x648c89, 0x8f9bae, 0x6f8caa];
const materials = {
  steel: material(0xbcc7cd, .36, .65), dark: material(0x415365, .48, .48),
  brass: material(0xb58d4d, .4, .55), white: material(0xe7ecf0, .65, .12),
  screen: material(0x223f56, .35, .3), black: material(0x26333e, .65, .2),
};

function material(color, roughness = .5, metalness = .3) {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness });
}
function box(parent, position, size, mat) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), mat);
  mesh.position.set(...position);
  mesh.castShadow = mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}
function cylinder(parent, position, radius, height, mat, rotation = [0, 0, 0]) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, height, 24), mat);
  mesh.position.set(...position);
  mesh.rotation.set(...rotation);
  mesh.castShadow = mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}
function typeFor(device) {
  const name = `${device.name || ''} ${device.model_filename || ''}`.toLowerCase();
  if (/泵|pump/.test(name)) return 'pump';
  if (/水箱|储罐|tank/.test(name)) return 'tank';
  if (/压缩|compress/.test(name)) return 'compressor';
  if (/控制|电气|传感|sensor|cabinet/.test(name)) return 'cabinet';
  if (/风机|fan/.test(name)) return 'fan';
  return 'engine';
}

function simplified(device, index) {
  const group = new THREE.Group();
  const shell = material(palette[index % palette.length], .44, .38);
  const { steel, dark, brass, white, screen, black } = materials;
  box(group, [0, .1, 0], [2.35, .2, 1.4], dark);
  for (const x of [-.9, .9]) for (const z of [-.48, .48]) {
    cylinder(group, [x, .2, z], .09, .16, steel);
  }
  switch (typeFor(device)) {
    case 'pump':
      cylinder(group, [-.62, .66, 0], .36, .78, shell, [0, 0, Math.PI / 2]);
      for (let i = 0; i < 7; i++) cylinder(group, [-.92 + i * .1, .66, 0], .39, .026, steel, [0, 0, Math.PI / 2]);
      cylinder(group, [.3, .63, 0], .43, .55, shell, [Math.PI / 2, 0, 0]);
      cylinder(group, [.3, .63, .36], .18, .25, steel, [Math.PI / 2, 0, 0]);
      cylinder(group, [.45, 1.08, 0], .15, .4, steel);
      cylinder(group, [.45, 1.3, 0], .22, .055, brass);
      box(group, [-.62, .32, 0], [.6, .25, .5], steel);
      break;
    case 'tank':
      cylinder(group, [0, 1.04, 0], .64, 1.6, shell);
      cylinder(group, [0, 1.88, 0], .65, .09, steel);
      cylinder(group, [0, .26, 0], .65, .08, steel);
      cylinder(group, [0, 2.03, 0], .12, .24, brass);
      box(group, [.2, 1.08, .65], [.065, 1.3, .04], steel);
      for (const y of [.4, 1.72]) cylinder(group, [.7, y, 0], .12, .37, brass, [0, 0, Math.PI / 2]);
      break;
    case 'cabinet':
      box(group, [0, 1.14, 0], [1.6, 1.94, .8], white);
      box(group, [0, 1.16, .42], [1.47, 1.8, .035], shell);
      box(group, [-.18, 1.63, .45], [.64, .42, .03], black);
      box(group, [-.18, 1.63, .47], [.54, .32, .02], screen);
      box(group, [.51, 1.05, .47], [.045, .37, .045], steel);
      for (let i = 0; i < 4; i++) cylinder(group, [-.44 + i * .22, 1.18, .47], .045, .03, i === 3 ? brass : steel, [Math.PI / 2, 0, 0]);
      for (let i = 0; i < 6; i++) box(group, [-.18, .48 + i * .055, .46], [.68, .015, .015], dark);
      break;
    case 'compressor':
      cylinder(group, [0, .6, 0], .4, 1.7, shell, [0, 0, Math.PI / 2]);
      box(group, [-.45, 1.14, 0], [.7, .5, .65], dark);
      cylinder(group, [.3, 1.12, 0], .28, .65, steel);
      cylinder(group, [.75, .86, 0], .08, .6, brass);
      break;
    case 'fan':
      cylinder(group, [0, 1.02, 0], .72, .65, shell, [Math.PI / 2, 0, 0]);
      cylinder(group, [0, 1.02, .35], .14, .16, steel, [Math.PI / 2, 0, 0]);
      for (let i = 0; i < 6; i++) {
        const blade = box(group, [0, 1.02, .35], [.12, 1.15, .06], steel);
        blade.rotation.z = i * Math.PI / 3;
      }
      box(group, [0, .38, 0], [1.3, .25, .8], dark);
      break;
    default:
      box(group, [-.2, .78, 0], [1.2, .85, .92], shell);
      box(group, [-.2, 1.28, 0], [1.34, .17, 1.02], dark);
      for (let i = 0; i < 4; i++) {
        box(group, [-.66 + i * .31, 1.42, 0], [.23, .16, .65], steel);
        cylinder(group, [-.66 + i * .31, 1.49, .25], .04, .16, brass);
      }
      cylinder(group, [.74, .77, 0], .42, .66, steel, [0, 0, Math.PI / 2]);
      box(group, [-.87, .86, 0], [.2, 1.05, 1.08], dark);
      for (let i = 0; i < 9; i++) box(group, [-.99, .43 + i * .1, 0], [.035, .025, .9], steel);
      cylinder(group, [.14, 1.69, -.3], .1, .54, dark);
      cylinder(group, [-.2, .55, .54], .065, .9, brass, [0, 0, Math.PI / 2]);
  }
  return group;
}

function disposeObject(object) {
  const geometries = new Set(), localMaterials = new Set(), textures = new Set();
  object.traverse(node => {
    if (node.geometry) geometries.add(node.geometry);
    if (node.material) for (const mat of Array.isArray(node.material) ? node.material : [node.material]) {
      if (Object.values(materials).includes(mat)) continue;
      localMaterials.add(mat);
      for (const value of Object.values(mat)) if (value?.isTexture) textures.add(value);
    }
  });
  geometries.forEach(x => x.dispose());
  textures.forEach(x => x.dispose());
  localMaterials.forEach(x => x.dispose());
  object.removeFromParent();
}

function fitModel(model) {
  model.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(model);
  const size = bounds.getSize(new THREE.Vector3());
  if (![size.x, size.y, size.z].every(Number.isFinite) || size.length() < .00001) throw new Error('Empty model');
  const scale = Math.min(2.7 / Math.max(size.x, .001), 2.15 / Math.max(size.y, .001), 1.8 / Math.max(size.z, .001));
  const normalizer = new THREE.Group();
  normalizer.add(model);
  normalizer.scale.setScalar(scale);
  normalizer.updateMatrixWorld(true);
  const scaled = new THREE.Box3().setFromObject(normalizer);
  const center = scaled.getCenter(new THREE.Vector3());
  normalizer.position.set(-center.x, -scaled.min.y + .02, -center.z);
  model.traverse(mesh => { if (mesh.isMesh) { mesh.castShadow = true; mesh.receiveShadow = true; } });
  return normalizer;
}

function updateOutline(asset) {
  if (asset.outline) disposeObject(asset.outline);
  const bounds = new THREE.Box3().setFromObject(asset.content);
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  asset.wrapper.worldToLocal(center);
  const outline = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(size.x + .12, size.y + .12, size.z + .12)),
    new THREE.LineBasicMaterial({ color: 0x4b83d4, transparent: true, opacity: .45 })
  );
  outline.position.copy(center);
  asset.wrapper.add(outline);
  asset.outline = outline;
}

async function loadConfigured(asset, version) {
  if (!asset.model_url) return;
  const controller = new AbortController();
  asset.controller = controller;
  let parsed;
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const url = new URL(asset.model_url, `${apiUrl}/`);
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Unsupported URL');
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const buffer = await response.arrayBuffer();
    const result = await loader.parseAsync(buffer, new URL('.', url).href);
    parsed = result.scene;
    if (version !== generation) { disposeObject(parsed); return; }
    if (controller.signal.aborted) throw new Error('Model loading timed out');
    const normalized = fitModel(parsed);
    disposeObject(asset.content);
    asset.content = normalized;
    asset.wrapper.add(normalized);
    asset.source = 'configured';
    updateOutline(asset);
  } catch (error) {
    if (version !== generation) return;
    if (parsed) disposeObject(parsed);
    asset.source = 'fallback';
  } finally {
    clearTimeout(timer);
    if (version === generation) { renderTree(); renderDetails(); updateSummary(); }
  }
}

function buildRoom() {
  [...room.children].forEach(disposeObject);
  const columns = Math.min(Math.max(assets.length, 1), 3), rows = Math.max(1, Math.ceil(assets.length / 3));
  const width = columns * 4 + 2, depth = rows * 3.6 + 4;
  const centerZ = -(rows - 1) * 1.8;
  box(room, [0, -.15, centerZ], [width, .25, depth], material(0xe3e9ef, .9, .05));
  const grid = new THREE.GridHelper(Math.max(width, depth), Math.max(width, depth) * 2, 0xc0cdd9, 0xd6e0e9);
  grid.position.set(0, -.018, centerZ);
  room.add(grid);
  box(room, [0, .38, centerZ - depth / 2], [width, .8, .14], material(0xdce4ed, .8));
  for (const x of [-width / 2 + .2, width / 2 - .2]) {
    box(room, [x, 1.5, centerZ - depth / 2], [.15, 3.2, .15], material(0xa6b7c6, .6, .3));
  }
  for (const asset of assets) {
    const [x, , z] = asset.position;
    box(room, [x, -.005, z], [3.4, .035, 2.75], material(0xd1dde8, .9, .05));
    for (const offset of [-1.7, 1.7]) box(room, [x + offset, .018, z], [.035, .018, 2.8], material(0xb7a36a, .8));
    box(room, [x, .018, z + 1.39], [3.4, .018, .035], material(0xb7a36a, .8));
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function sourceText(asset) {
  return asset.source === 'configured' ? '已配置模型' : asset.source === 'loading' ? '加载配置模型中' : '精简设备模型';
}
function renderTree() {
  const query = $('search').value.trim().toLowerCase();
  $('assetCount').textContent = `${assets.length} 台`;
  $('tree').innerHTML = assets.filter(a => `${a.name} ${a.id}`.toLowerCase().includes(query)).map(a =>
    `<button class="device-item ${selected === a ? 'active' : ''} ${alertIds.has(a.id) ? 'alarm' : ''}" data-device="${escapeHtml(a.id)}"><span class="device-name">${escapeHtml(a.name)}</span><span class="device-meta">${escapeHtml(a.station)} · ${sourceText(a)}</span></button>`
  ).join('') || '<div class="empty">没有匹配的设备</div>';
}
function renderDetails() {
  const a = selected;
  $('openDevice').disabled = !a;
  if (!a) { $('partName').textContent = '未配置设备'; return; }
  $('partName').textContent = a.name;
  $('partCode').textContent = a.id;
  $('partIndex').textContent = `${assets.indexOf(a) + 1} / ${assets.length}`;
  $('stationName').textContent = a.station;
  $('modelFile').textContent = a.model_filename || '内置精简模型';
  $('partStatus').textContent = alertIds.has(a.id) ? '设备告警' : alertServiceAvailable ? '未收到设备告警' : '暂无状态数据';
  $('modelState').classList.toggle('fallback', a.source === 'fallback');
  $('modelState').textContent = a.source === 'configured' ? '已加载配置模型' : a.source === 'loading' ? '正在加载配置模型，当前显示精简外形' : a.model_url ? '配置模型暂不可用，已显示精简设备外形' : '已显示内置精简设备模型';
  $('assemblyInfo').textContent = `${a.station} · 模型已居中并落地对齐。${a.source === 'configured' ? '使用系统设置中的模型文件。' : '精简外形仅用于设备空间定位。'}`;
}
function updateSummary() {
  const loaded = assets.filter(a => a.source === 'configured').length;
  const pending = assets.filter(a => a.source === 'loading').length;
  $('modelSummary').textContent = `${assets.length} 个工位 · ${loaded} 台配置模型 · ${assets.length - loaded} 台精简外形${pending ? `（${pending} 台加载中）` : ''}`;
  $('overviewTitle').textContent = mode === 'plant' ? '生产间设备装配' : '单机模型查看';
  host.dataset.modelCount = String(assets.length);
  host.dataset.configuredCount = String(loaded);
}
function select(asset) {
  selected = asset;
  renderTree();
  renderDetails();
}

function frameView(front = false) {
  const box = new THREE.Box3();
  for (const asset of assets) if (asset.wrapper.visible) box.expandByObject(asset.wrapper);
  if (box.isEmpty()) box.set(new THREE.Vector3(-3, 0, -2), new THREE.Vector3(3, 2, 2));
  const center = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
  const v = THREE.MathUtils.degToRad(camera.fov), aspect = Math.max(camera.aspect, .3);
  const distance = Math.max(size.y / (2 * Math.tan(v / 2)), size.x / (2 * Math.tan(v / 2) * aspect), size.z) * 1.4 + 2;
  controls.target.copy(center);
  camera.position.set(center.x, center.y + (front ? 0 : distance * .42), center.z + distance);
  camera.lookAt(center);
  controls.update();
}
function showPlant() {
  mode = 'plant';
  room.visible = true;
  assets.forEach(a => { a.wrapper.visible = true; a.wrapper.position.set(...a.position); });
  $('viewTitle').textContent = '工业生产间';
  $('viewSubtitle').textContent = '设备工位 / 模型装配';
  $('plantBtn').classList.add('active');
  $('frontBtn').classList.remove('active');
  frameView();
  updateSummary();
}
function showDevice() {
  if (!selected) return;
  mode = 'device';
  room.visible = false;
  assets.forEach(a => { a.wrapper.visible = a === selected; if (a === selected) a.wrapper.position.set(0, 0, 0); });
  $('viewTitle').textContent = selected.name;
  $('viewSubtitle').textContent = `${selected.station} / 单机模型`;
  $('plantBtn').classList.remove('active');
  frameView();
  updateSummary();
}

function setDevices(list) {
  const nextSignature = JSON.stringify(list.map(d => [d.id, d.name, d.model_url, d.model_filename]));
  if (signature === nextSignature) return;
  signature = nextSignature;
  const previousId = selected?.id;
  generation++;
  assets.forEach(a => { a.controller?.abort(); a.label.remove(); disposeObject(a.wrapper); });
  const columns = Math.min(3, list.length);
  assets = list.map((d, i) => {
    const row = Math.floor(i / 3), rowCount = Math.min(3, list.length - row * 3);
    const asset = {
      ...d, id: String(d.id), name: d.name || `工业设备 ${i + 1}`, station: `工位 ${String(i + 1).padStart(2, '0')}`,
      position: [(i % columns - (rowCount - 1) / 2) * 4, 0, row * -3.6], source: d.model_url ? 'loading' : 'fallback',
      wrapper: new THREE.Group(), label: document.createElement('div'),
    };
    asset.wrapper.position.set(...asset.position);
    asset.wrapper.userData.deviceId = asset.id;
    asset.content = simplified(asset, i);
    asset.wrapper.add(asset.content);
    equipment.add(asset.wrapper);
    asset.label.className = 'model-label';
    asset.label.textContent = `${asset.station} · ${asset.name}`;
    $('labels').appendChild(asset.label);
    updateOutline(asset);
    return asset;
  });
  select(assets.find(a => a.id === previousId) || assets[0] || null);
  buildRoom();
  showPlant();
  assets.forEach(a => loadConfigured(a, generation));
}

async function syncAlerts() {
  try {
    const response = await fetch(`${apiUrl}/api/alerts`, { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error('Alert service unavailable');
    const list = await response.json();
    if (!Array.isArray(list)) throw new Error('Invalid alerts');
    alertIds = new Set(list.filter(a => !a.handled && ['warning', 'danger', 'critical', 'high'].includes(a.level)).map(a => String(a.device_id || a.detail?.device_id || '')));
    alertServiceAvailable = true;
    $('serviceState').textContent = '告警接口已连接 · 传感数据待接入';
  } catch {
    alertServiceAvailable = false;
    alertIds.clear();
    $('serviceState').textContent = '服务未连接';
  }
  renderTree();
  renderDetails();
}

const raycaster = new THREE.Raycaster();
let down = null;
renderer.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
function pick(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  raycaster.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), camera);
  const visible = assets.filter(a => a.wrapper.visible).map(a => a.wrapper);
  for (const hit of raycaster.intersectObjects(visible, true)) {
    let object = hit.object;
    while (object && !object.userData.deviceId) object = object.parent;
    const asset = assets.find(a => a.id === object?.userData.deviceId);
    if (asset) { select(asset); return asset; }
  }
}
renderer.domElement.addEventListener('click', e => { if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 5) pick(e); });
renderer.domElement.addEventListener('dblclick', e => { if (pick(e)) showDevice(); });
$('tree').addEventListener('click', e => { const a = assets.find(a => a.id === e.target.closest('[data-device]')?.dataset.device); if (a) { select(a); if (mode === 'device') showDevice(); } });
$('search').oninput = renderTree;
$('plantBtn').onclick = showPlant;
$('openDevice').onclick = showDevice;
$('frontBtn').onclick = () => { frameView(true); $('frontBtn').classList.add('active'); };
$('resetBtn').onclick = () => { frameView(); $('frontBtn').classList.remove('active'); };
$('labelsBtn').onclick = () => { labelsVisible = !labelsVisible; $('labelsBtn').classList.toggle('active', labelsVisible); };
$('openSettings').onclick = () => { if (parent !== window) parent.postMessage({ type: 'equipment-settings', deviceId: selected?.id }, location.origin); };

let configuredByParent = false;
window.addEventListener('message', e => {
  if (e.source !== parent || e.origin !== location.origin || e.data?.type !== 'monitor-config') return;
  configuredByParent = true;
  apiUrl = String(e.data.apiUrl || location.origin).replace(/\/$/, '');
  setDevices(Array.isArray(e.data.devices) ? e.data.devices : []);
});
if (parent !== window) parent.postMessage({ type: 'equipment-ready' }, location.origin);
setTimeout(async () => {
  if (configuredByParent) return;
  try {
    const response = await fetch(`${apiUrl}/api/settings`, { signal: AbortSignal.timeout(8000) });
    if (!response.ok) throw new Error('No settings');
    const settings = await response.json();
    if (!configuredByParent) setDevices(Array.isArray(settings.devices) ? settings.devices : []);
  } catch { $('modelSummary').textContent = '设备配置读取失败，请检查本地服务'; }
}, 300);

function resize() {
  const width = Math.max(1, host.clientWidth), height = Math.max(1, host.clientHeight);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
}
new ResizeObserver(() => { resize(); if (host.clientWidth > 1 && host.clientHeight > 1) frameView(); }).observe(host);
resize();

const axis = $('axisCanvas'), ctx = axis.getContext('2d');
function drawAxis() {
  ctx.clearRect(0, 0, axis.width, axis.height);
  const inverse = camera.quaternion.clone().invert();
  const directions = [
    ['X', '#c35058', new THREE.Vector3(1, 0, 0)], ['Y', '#27896a', new THREE.Vector3(0, 1, 0)], ['Z', '#3974b5', new THREE.Vector3(0, 0, 1)],
  ].map(([text, color, vector]) => [text, color, vector.applyQuaternion(inverse)]).sort((a, b) => a[2].z - b[2].z);
  ctx.font = 'bold 17px Consolas, monospace';
  for (const [text, color, v] of directions) {
    ctx.strokeStyle = ctx.fillStyle = color;
    ctx.lineWidth = 3;
    const x = 65 + v.x * 42, y = 65 - v.y * 42;
    ctx.beginPath(); ctx.moveTo(65, 65); ctx.lineTo(x, y); ctx.stroke();
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
    ctx.fillText(text, x + (v.x < -.1 ? -17 : 7), y + (v.y > .1 ? -5 : 16));
  }
}
function animate() {
  requestAnimationFrame(animate);
  controls.update();
  if (host.clientWidth < 2 || host.clientHeight < 2) return;
  for (const a of assets) {
    const alarm = alertIds.has(a.id);
    if (a.outline) {
      a.outline.visible = alarm || selected === a;
      a.outline.material.color.setHex(alarm ? 0xd24b50 : 0x4b83d4);
      a.outline.material.opacity = alarm ? .45 + .5 * Math.abs(Math.sin(performance.now() / 220)) : .3;
    }
    const anchor = new THREE.Vector3(0, 2.45, 0).applyMatrix4(a.wrapper.matrixWorld).project(camera);
    a.label.hidden = !labelsVisible || !a.wrapper.visible || anchor.z < -1 || anchor.z > 1;
    a.label.style.left = `${(anchor.x + 1) * host.clientWidth / 2}px`;
    a.label.style.top = `${(1 - anchor.y) * host.clientHeight / 2}px`;
    a.label.className = `model-label ${selected === a ? 'active' : ''} ${alarm ? 'alarm' : ''}`;
  }
  renderer.render(scene, camera);
  drawAxis();
}
buildRoom();
frameView();
animate();
syncAlerts();
setInterval(syncAlerts, 5000);
