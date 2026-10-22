'use strict';

/* ---------- utilidades ---------- */
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const safeUrl = url => /^https?:\/\//i.test(url || '') ? esc(url) : '#';
const enc = encodeURIComponent;
const fold = text => String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const nf = new Intl.NumberFormat('es-PE');
const num = n => nf.format(n || 0);
const plural = (n, one, many) => `${num(n)} ${n === 1 ? one : many}`;
const PLATFORM = {youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram'};

function parseDate(value) {
  if (!value) return null;
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? value + 'T12:00:00' : value);
  return Number.isNaN(d.getTime()) ? null : d;
}
function fmtDate(value) {
  const d = parseDate(value);
  return d ? d.toLocaleDateString('es-PE', {day: 'numeric', month: 'short', year: 'numeric'}) : 'Sin fecha';
}
function fmtDateTime(value) {
  const d = parseDate(value);
  return d ? d.toLocaleString('es-PE', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}) : '';
}
const rtf = new Intl.RelativeTimeFormat('es', {numeric: 'auto'});
function relative(value) {
  const d = parseDate(value);
  if (!d) return '';
  const secs = (d.getTime() - Date.now()) / 1000, abs = Math.abs(secs);
  if (abs < 60) return 'ahora';
  if (abs < 3600) return rtf.format(Math.round(secs / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(secs / 3600), 'hour');
  return rtf.format(Math.round(secs / 86400), 'day');
}
const timecode = seconds => {
  const s = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, r = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${r}` : `${m}:${r}`;
};
const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* sin almacenamiento */ } },
};
function storedList(key) {
  try { const v = JSON.parse(store.get(key) || '[]'); return Array.isArray(v) ? v : []; } catch { return []; }
}

/* ---------- iconos ---------- */
const ICON = {
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 4.5 4.5"/>',
  create: '<rect x="2.5" y="6.5" width="13" height="11" rx="2"/><path d="m15.5 10.5 5-3v9l-5-3"/><path d="M9 9.5v5M6.5 12h5"/>',
  dashboard: '<rect x="3.5" y="3.5" width="7" height="8" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="5" rx="1.5"/><rect x="13.5" y="11.5" width="7" height="9" rx="1.5"/><rect x="3.5" y="14.5" width="7" height="6" rx="1.5"/>',
  content: '<rect x="3" y="7" width="14" height="13" rx="2"/><path d="M7 4h12a2 2 0 0 1 2 2v10"/><path class="f" d="m8.5 10.5 5 3-5 3Z"/>',
  bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.4 10.9c.6.4.9 1.1.9 1.8V16h5v-.3c0-.7.3-1.4.9-1.8A6 6 0 0 0 12 3Z"/>',
  history: '<path d="M4 12a8 8 0 1 0 2.3-5.6"/><path d="M4 4.5V8h3.5"/><path d="M12 8v4.5l3 1.8"/>',
  settings: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  flag: '<path d="M5.5 21V4.5h11.5l-1.8 4 1.8 4H5.5"/>',
  refresh: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5V9H15"/>',
  retry: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4.5 4.5V9H9"/>',
  more: '<circle class="f" cx="12" cy="5.5" r="1.6"/><circle class="f" cx="12" cy="12" r="1.6"/><circle class="f" cx="12" cy="18.5" r="1.6"/>',
  open: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  doc: '<path d="M7 3h7l5 5v13H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"/><path d="M14 3v5h5M9.5 13h6M9.5 17h6"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>',
  eyeoff: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><path d="M4 4l16 16"/>',
  alert: '<path d="M12 3.5 2.5 20h19L12 3.5Z"/><path d="M12 10v4.5"/><circle class="f" cx="12" cy="17.2" r="1"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8 12.3 2.7 2.7L16 9.5"/>',
  partial: '<circle cx="12" cy="12" r="9"/><path class="f" d="M12 3a9 9 0 0 1 0 18Z"/>',
  unknown: '<circle cx="12" cy="12" r="9" stroke-dasharray="3 3"/>',
  xcircle: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
  minus: '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><circle class="f" cx="12" cy="7.8" r="1"/>',
  filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  download: '<path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/>',
  down: '<path d="M12 5v14M6.5 13.5 12 19l5.5-5.5"/>',
  left: '<path d="m14.5 6-6 6 6 6"/>',
  right: '<path d="m9.5 6 6 6-6 6"/>',
  caret: '<path d="m7 10 5 5 5-5"/>',
  add: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
  paste: '<rect x="5" y="4.5" width="14" height="16" rx="2"/><path d="M9 4.5V3h6v1.5M9 10h6M9 14h6"/>',
  folder: '<path d="M3.5 6.5a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1V18a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1V6.5Z"/><path d="M12 11v5M9.5 13.5h5"/>',
  'person-add': '<circle cx="10" cy="8" r="3.5"/><path d="M3.5 20c.5-3.6 3.2-6 6.5-6 1.6 0 3 .5 4.1 1.4"/><path d="M18 14v6M15 17h6"/>',
  youtube: '<rect x="2.5" y="5.5" width="19" height="13" rx="4"/><path class="f" d="m10 9 5 3-5 3Z"/>',
  tiktok: '<path d="M14 4v10.5a3.5 3.5 0 1 1-3.5-3.5"/><path d="M14 4c.5 2.5 2.4 4.3 5 4.5"/>',
  instagram: '<rect x="3.5" y="3.5" width="17" height="17" rx="5"/><circle cx="12" cy="12" r="4"/><circle class="f" cx="17" cy="7" r="1"/>',
  play: '<circle cx="12" cy="12" r="9"/><path class="f" d="m10 8.5 5.5 3.5-5.5 3.5Z"/>',
  spark: '<path d="M12 3.5 13.8 9 19.5 10.8 13.8 12.6 12 18.5 10.2 12.6 4.5 10.8 10.2 9Z"/>',
};
const icon = (name, cls = '') => `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICON[name] || ''}</svg>`;
const platIcon = p => p in PLATFORM ? p : 'play';
function hydrateIcons(root = document) {
  root.querySelectorAll('svg[data-icon]').forEach(svg => {
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.innerHTML = ICON[svg.dataset.icon] || '';
    svg.removeAttribute('data-icon');
  });
}
// Anchos dinámicos sin estilos en línea (la CSP los bloquea).
function applyWidths(root = document) {
  root.querySelectorAll('[data-w]').forEach(el => { el.style.width = `${Math.max(0, Math.min(100, Number(el.dataset.w) || 0))}%`; });
}

/* ---------- estado ---------- */
const state = {
  catalog: {areas: [], people: [], sources: [], settings: {}},
  catalogKey: '',
  loaded: false,
  route: {view: '', id: '', sub: ''},
  overview: null,
  content: {area: '', q: ''},
  videos: {area: '', q: '', offset: 0, items: [], total: 0, hasMore: false, loading: false, key: ''},
  person: {id: '', q: '', offset: 0, items: [], total: 0, hasMore: false, loading: false, key: ''},
  k: {list: [], total: 0, hasMore: false, generatedAt: '', insights: [], reviewedAt: '', selected: null, pending: null,
    selectedOpen: false, onlyHits: false, personFilter: '', allInsights: false, version: 0},
  activeJob: store.get('creator-md-active-job'),
  activeSource: store.get('creator-md-active-source') || '',
  queue: storedList('creator-md-queue'),
  queueTotal: Number(store.get('creator-md-queue-total') || 0),
  job: null,
  currentSource: '',
  apifyConfigured: false,
};
const ACTIONS = {
  'skill-build': 'Construcción del skill',
  'skill-curation': 'Validación de criterios',
  'library-sync': 'Actualización', 'knowledge-build': 'Reconstrucción del índice', retry: 'Reintento',
  'recover-history': 'Recuperación de historial', sync: 'Búsqueda de novedades', pending: 'Procesar pendientes',
  preview: 'Análisis de perfil', extract: 'Extracción', single: 'Video individual', history: 'Continuar historial', continue: 'Continuar historial',
};
const JOB_STATUS = {completed: ['Terminada', 'ok', 'check'], running: ['En curso', 'run', 'refresh'], failed: ['Con error', 'err', 'xcircle'], interrupted: ['Interrumpida', 'warn', 'alert']};
const COVERAGE = {completa: ['check', 'Completa', 'Coincide con el total del proveedor'], parcial: ['partial', 'Parcial', 'Muestra o límite de consulta'], desconocida: ['unknown', 'Sin verificar', 'Aún sin listado completo']};
const TOPIC = {ventas: 'Ventas', creativos: 'Creativos', estructura: 'Estructura', medicion: 'Medición', general: 'General'};
const METHOD = {manual_import: 'Transcripción importada.', visual_ocr: 'Texto visual leído automáticamente con OCR.', visual_review: 'Notas de revisión visual.'};

/* ---------- API ---------- */
async function api(path, payload, method) {
  const init = payload === undefined && !method ? {} : {method: method || 'POST', headers: {'Content-Type': 'application/json'}, body: payload === undefined ? undefined : JSON.stringify(payload)};
  const response = await fetch(path, init);
  let data = {};
  try { data = await response.json(); } catch { /* respuesta vacía */ }
  if (!response.ok) {
    const error = new Error(data.error || 'No se pudo completar la solicitud.');
    error.status = response.status;
    throw error;
  }
  return data;
}

/* ---------- avisos ---------- */
function snack(message, kind = 'ok') {
  const el = document.createElement('div');
  el.className = `snack ${kind === 'error' ? 'err' : ''}`;
  el.innerHTML = `<p>${esc(message)}</p><button class="round round-sm" aria-label="Cerrar aviso">${icon('close')}</button>`;
  const close = () => { el.classList.add('leaving'); setTimeout(() => el.remove(), 160); };
  el.querySelector('button').onclick = close;
  $('snacks').append(el);
  if (kind !== 'error') setTimeout(close, 6000);
  while ($('snacks').children.length > 3) $('snacks').firstElementChild.remove();
}
const fail = error => snack(error.message || String(error), 'error');

function friendlyError(raw, platform) {
  const value = String(raw || '');
  if (!value) return '';
  if (platform === 'instagram') return 'Instagram limitó el acceso al historial. Los enlaces públicos ya encontrados se conservan; para ampliar la consulta puede hacer falta iniciar sesión.';
  if (/403|Forbidden/.test(value)) return 'La plataforma rechazó el acceso. Reintenta más tarde o importa la transcripción.';
  if (/Unexpected response|TikTok no respondió/.test(value)) return 'TikTok no respondió en la última consulta. Se conserva lo recopilado; vuelve a intentarlo en unos minutos.';
  if (/Command failed/.test(value)) return value.trim().split('\n').pop().replace(/^ERROR:\s*/, '').slice(0, 220);
  return value.slice(0, 260);
}

/* ---------- modelo ---------- */
const areaName = id => state.catalog.areas.find(a => a.id === id)?.name || id;
const personById = id => state.catalog.people.find(p => p.id === id);
const pcls = id => { const i = state.catalog.people.findIndex(p => p.id === id); return `pc-${(i < 0 ? 7 : i) % 8}`; };
const sourcesFor = person => state.catalog.sources.filter(s => s.person === person.id);
function sourceError(s) {
  const raw = s.status?.last_discovery_error || s.error || s.status?.error || '';
  return /requieren revisión o reintento/.test(raw) ? '' : raw;
}
function stats(s) {
  const t = s.status || {};
  const review = (t.failed || []).length + (t.needs_review || []).length;
  const error = sourceError(s);
  return {
    done: t.completed || 0, pending: t.pending || 0, review, error,
    checked: t.last_checked_at || (s.kind === 'single_video' ? s.last_success_at : null),
    coverage: t.coverage?.status || 'desconocida', reason: t.coverage?.reason || '',
    attention: review > 0 || !!error,
  };
}
function totals(sources) {
  return sources.reduce((acc, s) => {
    const st = stats(s);
    acc.done += st.done; acc.pending += st.pending; acc.review += st.review;
    if (st.error) acc.errors += 1;
    if (st.attention) acc.attention += 1;
    return acc;
  }, {done: 0, pending: 0, review: 0, errors: 0, attention: 0});
}
function sourceLabel(s) {
  let url;
  try { url = new URL(s.url); } catch { return {main: s.url, sub: ''}; }
  const parts = url.pathname.split('/').filter(Boolean);
  if (s.kind === 'single_video') return {main: 'Video individual', sub: url.searchParams.get('v') || parts.at(-1) || ''};
  let handle = ['channel', 'c', 'user'].includes(parts[0]) ? parts[1] : parts[0];
  handle = handle || url.hostname;
  if (!handle.startsWith('@') && s.platform !== 'youtube') handle = '@' + handle;
  const tab = {videos: 'Videos', shorts: 'Shorts', streams: 'Directos', reels: 'Reels'}[parts.at(-1)];
  return {main: handle, sub: tab || ''};
}
const initial = name => (String(name || '?').trim()[0] || '?').toUpperCase();
const avatar = (p, cls = '') => p ? `<span class="avatar ${cls} ${pcls(p.id)}" aria-hidden="true">${esc(initial(p.name))}</span>` : '';
const jobRunning = () => !!state.activeJob;
// Algunos videos llegan con la fecha como título: se muestra el inicio de lo que dice.
function vtitle(v) {
  const title = String(v.title || '').trim();
  if (title && !/^[A-Z][a-z]+ \d{1,2}, \d{4}$/.test(title)) return title;
  const segments = Array.isArray(v.segments) ? v.segments : v.preview || [];
  const said = (v.excerpt || segments.map(s => s.text).join(' ')).trim().split(/\s+/).slice(0, 12).join(' ');
  return said ? `«${said}…»` : title || 'Video sin título';
}
const lockAttr = () => jobRunning() ? 'disabled title="Hay una tarea en curso"' : '';
function ytId(url) {
  const m = /[?&]v=([\w-]{11})/.exec(url) || /youtu\.be\/([\w-]{11})/.exec(url) || /\/(?:shorts|embed|live)\/([\w-]{11})/.exec(url);
  return m ? m[1] : '';
}
function tileHTML(personId, platform, text) {
  return `<div class="tile ${pcls(personId)}">${icon(platIcon(platform))}<p>${esc(text)}</p></div>`;
}
function thumb({url, title, platform, person_id: personId}, cls = '') {
  const id = platform === 'youtube' ? ytId(url || '') : '';
  const data = `data-p="${esc(personId || '')}" data-pl="${esc(platform || '')}" data-t="${esc(String(title || '').slice(0, 140))}"`;
  return `<div class="thumb ${cls}" ${data}>${id ? `<img src="https://i.ytimg.com/vi/${id}/mqdefault.jpg" alt="" loading="lazy">` : tileHTML(personId, platform, title)}</div>`;
}
function sourceThumb(s, cls = '') {
  const latest = state.overview?.areas?.[s.category]?.source_latest?.[s.id]
    || Object.values(state.overview?.areas || {}).map(a => a.source_latest?.[s.id]).find(Boolean);
  if (latest) return thumb({url: latest.url, title: latest.title, platform: s.platform, person_id: s.person}, cls);
  if (s.kind === 'single_video' && s.platform === 'youtube') return thumb({url: s.url, title: 'Video individual', platform: s.platform, person_id: s.person}, cls);
  return thumb({url: '', title: sourceLabel(s).main, platform: s.platform, person_id: s.person}, cls);
}
// Si una miniatura no carga (sin red o bloqueada), se sustituye por una tarjeta de color.
document.addEventListener('error', event => {
  const img = event.target;
  if (img.tagName !== 'IMG' || !img.parentElement?.classList.contains('thumb')) return;
  const box = img.parentElement;
  box.innerHTML = tileHTML(box.dataset.p, box.dataset.pl, box.dataset.t);
}, true);

/* ---------- rutas ---------- */
const VIEWS = ['panel', 'contenido', 'persona', 'conocimiento', 'skills', 'actividad'];
const TITLES = {panel: 'Panel', contenido: 'Contenido', persona: 'Persona', conocimiento: 'Conocimiento', skills: 'Skills', actividad: 'Actividad'};
function parseRoute() {
  const parts = location.hash.slice(1).split('/').map(p => { try { return decodeURIComponent(p); } catch { return p; } });
  let view = parts[0] || 'panel';
  if (view === 'biblioteca') view = 'panel';
  if (view === 'configuracion') { view = 'panel'; setTimeout(openSettings, 0); }
  if (!VIEWS.includes(view)) view = 'panel';
  return ['persona', 'skills'].includes(view) ? {view, id: parts[1] || '', sub: parts[2] || ''} : {view, id: '', sub: parts[1] || ''};
}
function go(hash) {
  if (location.hash === hash) route(); else location.hash = hash;
}
function route() {
  const prev = state.route;
  state.route = parseRoute();
  const r = state.route;
  const changed = prev.view !== r.view || prev.id !== r.id || prev.sub !== r.sub;
  VIEWS.forEach(v => { $(`view-${v}`).hidden = v !== r.view; });
  const person = r.view === 'persona' ? personById(r.id) : null;
  document.title = `${person ? person.name : TITLES[r.view]} · Creator MD`;
  if (changed) window.scrollTo(0, 0);
  closeReader();
  if (matchMedia('(max-width: 1100px)').matches) setSide(false);
  renderSide();
  renderView(changed);
}
function renderView(changed = false) {
  if (!state.loaded) return;
  const r = state.route;
  if (r.view === 'panel') renderPanel();
  if (r.view === 'contenido') {
    renderContenido();
    if (r.sub === 'videos' && (changed || !state.videos.key)) loadVideos(true);
  }
  if (r.view === 'persona') {
    if (state.person.id !== r.id) loadPerson(r.id);
    renderPersona();
  }
  if (r.view === 'conocimiento') {
    renderAreaSelect();
    if (changed) searchKnowledge().catch(fail); else renderPersonFilters();
  }
  if (r.view === 'actividad' && changed) loadActivity().catch(fail);
  if (r.view === 'skills' && (changed || !skillsState.loaded)) loadSkills().catch(fail);
  renderJobUI();
}
// Conserva el foco y el cursor al volver a pintar una vista.
function keepFocus(fn) {
  const active = document.activeElement;
  const id = active?.id, start = active?.selectionStart, end = active?.selectionEnd;
  fn();
  if (id && $(id) && $(id) !== active) {
    $(id).focus();
    try { $(id).setSelectionRange(start, end); } catch { /* no es un campo de texto */ }
  }
}

/* ---------- proyectos de skill ---------- */
const skillsState = {loaded: false, serial: 0, projects: [], selected: null, preview: null};
const SKILL_STATUS = {draft: 'Borrador: falta revisar', ready: 'Criterios con referencias', needs_review: 'Revisión pendiente'};
function skillPeopleHTML(selectedPeople) {
  return state.catalog.people.map(p => {
    const sources = sourcesFor(p), count = totals(sources).done;
    return `<label class="skill-person"><input type="checkbox" name="person_ids" value="${esc(p.id)}" ${selectedPeople.has(p.id) ? 'checked' : ''}><span><strong>${esc(p.name)}</strong><small>${esc(areaName(p.area))} · ${plural(sources.length, 'fuente', 'fuentes')} · ${plural(count, 'video procesado', 'videos procesados')}</small><small>${esc([...new Set(sources.map(x => PLATFORM[x.platform] || x.platform))].join(' · '))}</small></span></label>`;
  }).join('') || '<p>No hay personas todavía. Añade una persona o canal a la biblioteca para usar sus fuentes.</p>';
}
async function loadSkills() {
  const serial = ++skillsState.serial;
  const selectedId = state.route.id;
  const result = await api('/api/skills');
  let selected = null, preview = null;
  if (selectedId && selectedId !== 'nuevo') {
    [selected, preview] = await Promise.all([
      api('/api/skills/' + enc(selectedId)), api('/api/skills/' + enc(selectedId) + '/preview'),
    ]);
  }
  if (serial !== skillsState.serial || state.route.view !== 'skills' || state.route.id !== selectedId) return;
  Object.assign(skillsState, {loaded: true, projects: result.projects || [], selected, preview});
  renderSkills();
}
function renderSkills() {
  const s = skillsState, project = s.selected;
  const editing = state.route.id === 'nuevo' || !!project;
  const preview = s.preview;
  const selectedPeople = new Set(project?.person_ids || []);
  const status = preview?.status || project?.status || 'draft';
  const statusText = SKILL_STATUS[status] || status;
  const review = preview?.review_request || '';
  $('view-skills').innerHTML = `
    <div class="page-head"><div><h1 id="skills-title">Skills</h1><p class="page-sub">Convierte lo que aprendiste de una o varias personas en un método que puedas aplicar.</p></div><a class="pill pill-solid" href="#skills/nuevo">${icon('add')}Crear skill</a></div>
    <div class="skill-workspace">
      <nav class="skill-project-list" aria-label="Tus proyectos de skill">
        <h2>Tus skills</h2>
        ${s.projects.length ? s.projects.map(p => `<a href="#skills/${enc(p.id)}" ${p.id === project?.id ? 'aria-current="page"' : ''}><strong>${esc(p.name)}</strong><span>${esc(p.purpose)}</span><small>${plural(p.person_ids?.length || 0, 'persona', 'personas')}${p.last_build?.built_at ? ` · ${esc(fmtDate(p.last_build.built_at))}` : ''}</small></a>`).join('') : '<p class="sub">Todavía no has creado un proyecto. Puedes combinar personas de distintas áreas.</p>'}
      </nav>
      ${editing ? `<div class="skill-editor">
        <form id="skill-project-form" class="card" data-project="${esc(project?.id || '')}">
          <h2>${project ? 'Configurar skill' : 'Nuevo skill'}</h2>
          <p class="sub skill-intro">Define qué tiene que resolver y de quién tomará sus fuentes. El paquete guarda la evidencia y distingue los criterios revisados.</p>
          <label class="field"><span>Nombre del skill</span><input class="input" id="skill-name" name="name" required maxlength="100" value="${esc(project?.name || '')}" placeholder="Ads para negocios locales"></label>
          <label class="field"><span>¿Qué debe ayudar a conseguir?</span><textarea class="input" id="skill-purpose" name="purpose" rows="2" required maxlength="1500" placeholder="Diagnosticar por qué los anuncios generan consultas pero pocas ventas.">${esc(project?.purpose || '')}</textarea></label>
          <label class="field"><span>¿Para quién o para qué tipos de negocio?</span><textarea class="input" id="skill-audience" name="audience" rows="2" maxlength="1000" placeholder="Equipos pequeños, tiendas y servicios que venden por WhatsApp.">${esc(project?.audience || '')}</textarea></label>
          <label class="field"><span>Tareas que debe saber hacer</span><textarea class="input" id="skill-tasks" name="tasks" rows="4" required maxlength="6000" placeholder="Diagnosticar el embudo&#10;Proponer una prueba de anuncios&#10;Revisar el costo de adquirir un cliente">${esc((project?.tasks || []).join('\n'))}</textarea><small>Una tarea por línea. Describe decisiones o entregables concretos.</small></label>
          <fieldset class="field"><legend>Personas y fuentes</legend><p class="sub">Selecciona una o varias personas. Sus fuentes permanecen en la biblioteca.</p>
            <div class="skill-people">${skillPeopleHTML(selectedPeople)}</div>
            <button type="button" class="link-btn" data-add="">Añadir persona a la biblioteca</button>
          </fieldset>
          <label class="skill-auto"><input type="checkbox" name="auto_update" ${project?.auto_update !== false ? 'checked' : ''}><span>Actualizar este paquete cuando se actualice la biblioteca<small>La extracción respeta las fuentes pausadas y los límites configurados. El contenido nuevo sigue pendiente de revisión hasta contrastarlo.</small></span></label>
          <p class="form-error" id="skill-form-error" role="alert"></p>
          <div class="actions skill-form-actions"><button class="pill pill-line" type="submit" value="save">Guardar borrador</button><button class="pill pill-solid" type="submit" value="build" ${jobRunning() ? 'disabled' : ''}>${icon('refresh')}Guardar y construir</button></div>
        </form>
        ${project ? `<section class="card skill-evidence" aria-labelledby="skill-evidence-title"><div class="page-head"><h2 id="skill-evidence-title">Contenido del paquete</h2><span class="status st-${status === 'ready' ? 'ok' : 'warn'}">${esc(statusText)}</span></div>
          <dl class="skill-counts"><div><dt>Videos disponibles</dt><dd>${num(preview?.evidence_count)}</dd></div><div><dt>Criterios revisados</dt><dd>${num(preview?.curated_count)}</dd></div><div><dt>Personas elegidas</dt><dd>${num(project.person_ids?.length)}</dd></div></dl>
          <p class="sub">${status === 'ready' ? 'Los criterios incluyen referencias y condiciones de aplicación. Revisa que correspondan al negocio y a la tarea antes de usarlos.' : status === 'needs_review' ? 'Hay criterios que necesitan revisión por cambios en las fuentes, la selección o el propósito. Comprueba su aplicación al nuevo contexto antes de usarlos.' : 'El archivo organiza las fuentes, pero todavía necesita una síntesis revisada para convertirse en un método fiable. Construirlo no valida las afirmaciones del creador.'}</p>
          ${preview?.needs_rebuild ? '<p class="skill-notice">Hay cambios desde la última construcción. Guarda y construye para incluirlos.</p>' : ''}
          ${Array.isArray(preview?.sources) && preview.sources.length ? `<details class="skill-source-details"><summary>Ver estado de las fuentes</summary><ul>${preview.sources.map(source => {
            const current = state.catalog.sources.find(s => s.id === source.id) || source;
            const st = stats(current), coverage = COVERAGE[st.coverage]?.[1] || 'Sin verificar';
            return `<li><strong>${esc(personById(source.person)?.name || source.project || source.id)}</strong> · ${esc(PLATFORM[source.platform] || source.platform || '')}${source.enabled === false ? ' · Pausada' : ''}<br><span class="sub">Cobertura ${esc(coverage.toLowerCase())} · ${plural(st.done, 'video procesado', 'videos procesados')}${st.pending ? ` · ${num(st.pending)} pendientes` : ''}${st.checked ? ` · Consultada ${esc(fmtDate(st.checked))}` : ''}${st.error ? ` · ${esc(friendlyError(st.error, source.platform))}` : ''}</span></li>`;
          }).join('')}</ul></details>` : ''}
          <div class="actions skill-form-actions">${preview?.export_ready ? `<a class="pill pill-line" href="/api/skills/${enc(project.id)}/download" download="${esc(project.id)}.zip">${icon('download')}Descargar último paquete</a>` : '<p class="sub">Completa la construcción del skill para preparar su archivo ZIP.</p>'}</div>
          ${review ? `<details class="skill-review-request"><summary>Preparar la revisión con tu IA</summary><p class="sub">Entrega el paquete y esta petición a tu agente. Creator MD no llama a una API de IA al construirlo.</p><label class="field"><span>Petición de revisión</span><textarea class="input" id="skill-review-request" rows="10" readonly>${esc(review)}</textarea></label><button type="button" class="pill pill-line" data-copy-review>${icon('copy')}Copiar petición</button></details>` : ''}
          ${project.last_build ? `<details class="skill-review-request"><summary>Incorporar criterios revisados</summary><p class="sub">Después de revisar las fuentes, pega el JSON de síntesis que preparó tu agente. Se comprueban su estructura y referencias; eso no demuestra que las afirmaciones sean verdaderas.</p><form id="skill-curation-form" data-project="${esc(project.id)}"><label class="field"><span>JSON de criterios</span><textarea class="input skill-json" id="skill-curation-json" name="curation" rows="10" required spellcheck="false" placeholder="Pega aquí el JSON con el formato indicado en la petición de revisión."></textarea></label><p class="form-error" id="skill-curation-error" role="alert"></p><button class="pill pill-line" type="submit">Validar y guardar criterios</button></form></details>` : ''}
        </section>` : ''}
      </div>` : `<div class="card skill-welcome"><h2>Un proyecto, un propósito</h2><p>Reúne las personas que te sirven para una tarea y prepara un skill independiente de esta aplicación.</p><p>Empieza con sus fuentes, revisa qué afirmaciones tienen respaldo y conserva los límites para adaptarlas a otros contextos.</p><a class="pill pill-solid" href="#skills/nuevo">Crear mi primer skill</a></div>`}
    </div>`;
}
async function saveSkillProject(form, build) {
  const data = new FormData(form);
  const payload = {name: data.get('name'), purpose: data.get('purpose'), audience: data.get('audience'),
    tasks: String(data.get('tasks') || '').split('\n').map(x => x.trim()).filter(Boolean),
    person_ids: data.getAll('person_ids'), auto_update: data.has('auto_update')};
  const error = $('skill-form-error');
  error.textContent = '';
  if (build && jobRunning()) { error.textContent = 'Espera a que termine la tarea en curso para construir este skill.'; return; }
  if (!payload.person_ids.length) { error.textContent = 'Selecciona al menos una persona.'; return; }
  submitting(form, true);
  try {
    const saved = await api('/api/skills' + (form.dataset.project ? '/' + enc(form.dataset.project) : ''), payload);
    if (build) await startJob('skills/' + enc(saved.id) + '/build', {}, null);
    snack(build ? 'Construcción iniciada. Puedes seguir su progreso en Actividad.' : 'Borrador guardado.');
    if (state.route.id === saved.id) await loadSkills(); else go('#skills/' + enc(saved.id));
  } catch (e) { error.textContent = e.message; }
  finally { if (form.isConnected) submitting(form, false); }
}
async function saveSkillCuration(form) {
  const error = $('skill-curation-error');
  error.textContent = '';
  let payload;
  if (jobRunning()) { error.textContent = 'Espera a que termine la tarea en curso para validar los criterios.'; return; }
  try { payload = JSON.parse(new FormData(form).get('curation')); }
  catch { error.textContent = 'El texto no es JSON válido. Pega solo el objeto JSON, sin bloques de código ni comentarios.'; return; }
  submitting(form, true);
  try {
    await startJob('skills/' + enc(form.dataset.project) + '/curation', payload);
    snack('Validación iniciada. Si las referencias son válidas se actualizará el paquete.');
  } catch (e) { error.textContent = e.message; }
  finally { if (form.isConnected) submitting(form, false); }
}

/* ---------- barra lateral ---------- */
function setSide(open) {
  document.body.classList.toggle('side-open', open);
  $('scrim').hidden = !open || !matchMedia('(max-width: 1100px)').matches;
  $('menu-toggle').setAttribute('aria-expanded', String(open || (!matchMedia('(max-width: 1100px)').matches && !document.body.classList.contains('side-mini'))));
}
function renderSide() {
  const {areas, people, settings, sources} = state.catalog;
  const r = state.route;
  const person = r.view === 'persona' ? personById(r.id) : null;
  if (person) {
    $('side-id').innerHTML = `<a href="#persona/${enc(person.id)}">${avatar(person)}<b>${esc(person.name)}</b><small>${esc(areaName(person.area))} · ${plural(sourcesFor(person).length, 'fuente', 'fuentes')}</small></a>`;
  } else {
    $('side-id').innerHTML = `<span class="avatar lib" aria-hidden="true">CM</span><b>Tu biblioteca</b><small>${esc(areas.map(a => a.name).join(' · ') || 'En este equipo')}</small>`;
  }
  document.querySelectorAll('#main-nav a').forEach(a => a.classList.toggle('on', a.dataset.route === r.view));
  const t = totals(sources);
  $('nav-attention').textContent = t.attention || '';
  $('nav-attention').title = t.attention ? plural(t.attention, 'fuente con avisos', 'fuentes con avisos') : '';
  $('side-people').innerHTML = areas.map(a => {
    const list = people.filter(p => p.area === a.id);
    return `<div class="side-label"><span>${esc(a.name)}</span><button class="round" data-add-area="${esc(a.id)}" title="Añadir persona a ${esc(a.name)}" aria-label="Añadir persona a ${esc(a.name)}">${icon('add')}</button></div>
      <div class="nav people">${list.map(p => `<a href="#persona/${enc(p.id)}" class="${p.id === r.id ? 'on' : ''}">${avatar(p, 'avatar-sm')}<span>${esc(p.name)}</span><span class="count">${num(totals(sourcesFor(p)).done)}</span></a>`).join('')
      || '<p class="side-status">Sin personas todavía.</p>'}</div>`;
  }).join('');
  if (settings.enabled) {
    const next = sources.filter(s => s.enabled && s.next_run_at).map(s => s.next_run_at).sort()[0];
    $('schedule-state').innerHTML = `<span class="dot ok"></span><span>Automática cada ${esc(settings.interval_hours)} h${next ? ` · próxima ${esc(relative(next))}` : ''}</span>`;
  } else {
    $('schedule-state').innerHTML = `<span class="dot"></span><span>Actualización manual</span>`;
  }
  $('area-options').innerHTML = areas.map(a => `<option value="${esc(a.name)}">`).join('');
  $('person-options').innerHTML = people.map(p => `<option value="${esc(p.name)}">`).join('');
}

/* ---------- resumen de conocimiento ---------- */
async function loadOverview() {
  try {
    state.overview = await api('/api/overview');
  } catch (e) {
    if (e.status !== 404) throw e;
    // Servidor sin reiniciar: se reconstruye lo esencial con la búsqueda existente.
    const areas = {};
    for (const a of state.catalog.areas) {
      try {
        const k = await api('/api/knowledge?' + new URLSearchParams({area: a.id, q: '', offset: 0}));
        const sourceLatest = {};
        for (const v of k.videos) if (v.source_id && !sourceLatest[v.source_id]) sourceLatest[v.source_id] = {url: v.url, title: v.title};
        areas[a.id] = {
          generated_at: k.generated_at, videos: k.total || 0, topics: [], months: {}, partial: true, source_latest: sourceLatest,
          latest: k.videos.slice(0, 12).map(v => ({...v, segments: v.segments.length, preview: v.segments.slice(0, 3)})),
          insights: (k.curated?.insights || []).map(i => ({id: i.id, title: i.title, cites: i.evidence.length})),
          reviewed_at: k.curated?.reviewed_at,
        };
      } catch { areas[a.id] = {videos: 0, topics: [], months: {}, latest: [], insights: [], partial: true, source_latest: {}}; }
    }
    state.overview = {areas, partial: true};
  }
  if (['panel', 'persona', 'contenido'].includes(state.route.view)) keepFocus(() => renderView());
}
const ovAreas = () => Object.entries(state.overview?.areas || {});

/* ---------- panel ---------- */
function renderPanel() {
  const el = $('view-panel');
  const {people, sources, areas, settings} = state.catalog;
  if (!people.length) {
    el.innerHTML = `<div class="welcome">${icon('content')}<h1 id="panel-title">Tu biblioteca empieza con un enlace</h1>
      <p>Creator MD recopila los videos públicos de las personas que sigues y conserva cada transcripción con sus tiempos.</p>
      <ol><li>Añade una persona y pega los enlaces de sus canales.</li><li>Pulsa Actualizar para transcribir sus videos.</li><li>Busca en Conocimiento y descarga el skill del área.</li></ol>
      <div class="actions"><button class="pill pill-solid" data-add="">${icon('person-add')}Añadir persona</button>${areas.length ? '' : `<button class="pill pill-line" data-new-area>${icon('folder')}Área nueva</button>`}</div></div>`;
    return;
  }
  const t = totals(sources);
  const ov = state.overview;
  const latestAll = ovAreas().flatMap(([area, a]) => (a.latest || []).map(v => ({...v, area}))).sort((a, b) => String(b.published_at || '').localeCompare(String(a.published_at || '')));
  const latest = latestAll.find(v => ytId(v.url || '')) || latestAll[0];
  const issues = sources.filter(s => stats(s).attention).sort((a, b) => (stats(b).error ? 1 : 0) - (stats(a).error ? 1 : 0) || stats(b).review - stats(a).review);
  const ranking = people.map(p => ({p, done: totals(sourcesFor(p)).done})).sort((a, b) => b.done - a.done);
  const topicMap = {};
  ovAreas().forEach(([, a]) => (a.topics || []).forEach(([k, v]) => { topicMap[k] = (topicMap[k] || 0) + v; }));
  const topics = Object.entries(topicMap).sort((a, b) => b[1] - a[1]);
  const maxTopic = topics[0]?.[1] || 1;
  const next = sources.filter(s => s.enabled && s.next_run_at).map(s => s.next_run_at).sort()[0];
  const sk = '<div class="card sk sk-card"></div>';

  const latestCard = !ov ? sk : latest ? `<section class="card latest">
      <h2>Última transcripción</h2>
      <button class="thumb-btn" data-open-video="${esc(latest.area)}|${esc(latest.id)}" aria-label="Leer la transcripción">${thumb(latest, 'thumb-lg')}</button>
      <h3>${esc(vtitle(latest))}</h3>
      <p class="meta">${icon(platIcon(latest.platform), 'ic-xs')}${esc(latest.person)} · ${esc(fmtDate(latest.published_at))}</p>
      <div class="kv"><span>Fragmentos con tiempo</span><b>${num(latest.segments)}</b></div>
      <div class="kv"><span>Palabras</span><b>${num(latest.words)}</b></div>
      <div class="kv"><span>Temas</span><b>${esc((latest.topics || []).map(x => TOPIC[x] || x).join(', '))}</b></div>
      <div class="card-foot"><button class="link-btn" data-open-video="${esc(latest.area)}|${esc(latest.id)}">Leer transcripción</button><a class="link-btn" href="${safeUrl(latest.url)}" target="_blank" rel="noopener noreferrer">Ver original</a></div>
    </section>` : `<section class="card"><h2>Última transcripción</h2><div class="empty">${icon('content')}<h3>Aún no hay transcripciones</h3><p>Actualiza tus fuentes para empezar.</p></div></section>`;

  const attentionCard = `<section class="card">
      <h2>Necesitan tu atención</h2>
      ${issues.length ? `<p class="sub">${t.errors ? `${plural(t.errors, 'fuente sin respuesta', 'fuentes sin respuesta')} · ` : ''}${plural(t.review, 'video por revisar', 'videos por revisar')}</p>
      <div>${issues.slice(0, 4).map(s => {
        const st = stats(s), p = personById(s.person);
        return `<div class="issue">${st.error ? `<span class="err-text">${icon('alert')}</span>` : `<span class="warn-text">${icon('retry')}</span>`}
          <div><b>${esc(p?.name || s.project)} · ${esc(PLATFORM[s.platform] || s.platform)}</b>
          <p>${st.error ? esc(friendlyError(st.error, s.platform)) : `${plural(st.review, 'video no se pudo procesar', 'videos no se pudieron procesar')}.`}</p>
          <div class="acts">${st.review ? `<button class="pill pill-line pill-sm" data-retry="${esc(s.id)}" ${lockAttr()}>${icon('retry')}Reintentar</button>` : ''}<button class="pill pill-line pill-sm" data-sync="${esc(s.id)}" ${lockAttr()}>${icon('refresh')}Consultar</button></div></div></div>`;
      }).join('')}</div>
      <div class="card-foot"><a class="link-btn" href="#contenido/revisar">Ver ${issues.length > 4 ? `las ${issues.length} fuentes` : 'en Contenido'}</a></div>`
      : `<div class="sched">${icon('check')}<span>Todo al día. Ninguna fuente tiene avisos.</span></div>`}
    </section>`;

  const stateCard = `<section class="card">
      <h2>Estado de la biblioteca</h2>
      <p class="sub">Videos procesados</p>
      <p class="big">${num(t.done)}</p>
      <p class="big-sub">${t.review ? `<span class="warn-text">${num(t.review)} por revisar</span> · ` : ''}${plural(t.pending, 'pendiente', 'pendientes')}</p>
      <div class="rule"></div>
      <p class="section-t">Resumen</p>
      <div class="kv"><span>Personas</span><b>${num(people.length)}</b></div>
      <div class="kv"><span>Fuentes conectadas</span><b>${num(sources.length)}</b></div>
      <div class="kv"><span>Cobertura completa</span><b>${sources.filter(s => stats(s).coverage === 'completa').length} de ${sources.length}</b></div>
      <div class="rule"></div>
      <p class="section-t">Más procesados</p>
      <div class="row-head"><span>Persona</span><span>Videos</span></div>
      ${ranking.slice(0, 6).map(({p, done}) => `<a class="rank" href="#persona/${enc(p.id)}">${avatar(p, 'avatar-sm')}<span class="name">${esc(p.name)}</span><span class="num">${num(done)}</span></a>`).join('')}
      <div class="card-foot"><a class="link-btn" href="#contenido">Ir a Contenido</a></div>
    </section>`;

  const topicsCard = topics.length ? `<section class="card">
      <h2>Temas en tus transcripciones</h2>
      <p class="sub">Clasificación automática por palabras clave</p>
      <div class="bars">${topics.map(([k, v]) => `<div class="bar-row"><div><span>${esc(TOPIC[k] || k)}</span><span class="num">${num(v)}</span></div><div class="bar"><span data-w="${(v / maxTopic * 100).toFixed(1)}"></span></div></div>`).join('')}</div>
    </section>` : '';

  const recentCard = !ov ? sk : `<section class="card">
      <h2>Videos recientes</h2>
      ${latestAll.length ? `<div class="vlist">${latestAll.slice(0, 5).map(v => `<button class="vrow" data-open-video="${esc(v.area)}|${esc(v.id)}">${thumb(v, 'thumb-sm')}<div><h4>${esc(vtitle(v))}</h4><span>${esc(v.person)} · ${esc(fmtDate(v.published_at))}</span></div></button>`).join('')}</div>
      <div class="card-foot"><a class="link-btn" href="#contenido/videos">Ver todos los videos</a></div>` : '<p class="sub">Aparecerán aquí al procesar tus fuentes.</p>'}
    </section>`;

  const insightAreas = ovAreas().filter(([, a]) => (a.insights || []).length);
  const insightsCard = !ov ? '' : `<section class="card">
      <h2>Criterios revisados</h2>
      ${insightAreas.length ? insightAreas.map(([area, a]) => `<p class="sub">${esc(areaName(area))} · síntesis con citas${a.reviewed_at ? ` · ${esc(fmtDate(a.reviewed_at))}` : ''}</p>
        <div class="vlist">${a.insights.map(i => `<button class="ins" data-open-insight="${esc(area)}|${esc(i.id)}">${icon('spark')}<span><b>${esc(i.title)}</b><small>${plural(i.cites, 'cita', 'citas')}</small></span></button>`).join('')}</div>`).join('')
        : '<p class="sub">Todavía no hay síntesis revisadas. El skill puede usarse igualmente con la evidencia.</p>'}
      <div class="card-foot">${areas.map(a => (state.overview?.areas?.[a.id]?.videos || 0) > 0
        ? `<a class="link-btn" href="/skill?area=${enc(a.id)}" download="${esc(a.id)}-evidence.zip">${icon('download')}Skill de ${esc(a.name)}</a>` : '').join('')}</div>
    </section>`;

  const schedCard = `<section class="card">
      <h2>Actualización automática</h2>
      <div class="sched ${settings.enabled ? '' : 'off'}">${icon(settings.enabled ? 'check' : 'info')}<span>${settings.enabled ? `Cada ${esc(settings.interval_hours)} h${next ? ` · próxima ${esc(relative(next))}` : ''}` : 'Desactivada: actualizas a mano'}</span></div>
      <div class="kv"><span>Modelo de transcripción</span><b>${esc(settings.model || 'base')}</b></div>
      <div class="kv"><span>Máximo por fuente</span><b>${num(settings.process_limit || 50)} videos</b></div>
      <div class="card-foot"><button class="link-btn" data-open-settings>Editar</button></div>
    </section>`;

  el.innerHTML = `<div class="page-head"><h1 id="panel-title">Panel de la biblioteca</h1>
      <div class="actions"><button class="pill pill-line" data-sync-all ${lockAttr()}>${icon('refresh')}Actualizar todo</button><button class="pill pill-solid" data-add="">${icon('person-add')}Añadir persona</button></div></div>
    <div class="dash">
      <div class="dash-col">${latestCard}${attentionCard}</div>
      <div class="dash-col">${stateCard}${topicsCard}</div>
      <div class="dash-col c3">${recentCard}${insightsCard}${schedCard}</div>
    </div>`;
  applyWidths(el);
}

/* ---------- contenido ---------- */
function defaultArea() {
  const withVideos = ovAreas().sort((a, b) => (b[1].videos || 0) - (a[1].videos || 0))[0]?.[0];
  return state.content.area || withVideos || state.catalog.areas[0]?.id || '';
}
function sourceRow(s) {
  const st = stats(s), label = sourceLabel(s), p = personById(s.person), single = s.kind === 'single_video';
  const total = st.done + st.review + st.pending;
  const pct = total ? Math.round(st.done / total * 100) : 0;
  const busy = jobRunning() && state.activeSource === s.id;
  const [cIcon, cLabel, cSub] = single ? ['youtube', 'Video suelto', 'Se procesa una vez'] : COVERAGE[st.coverage] || COVERAGE.desconocida;
  const warn = busy
    ? `<div class="cell-icon st-run"><span class="ring"></span><div>Actualizando<small>${num(state.job?.percent || 0)} %</small></div></div>`
    : st.error ? `<div class="cell-icon err-text">${icon('alert')}<div>Sin respuesta<small>${esc(friendlyError(st.error, s.platform))}</small></div></div>`
    : st.review ? `<div class="cell-icon warn-text">${icon('retry')}<div>${num(st.review)} por revisar<small>Reintenta o importa el texto</small></div></div>`
    : st.pending ? `<div class="cell-icon muted">${icon('history')}<div>${plural(st.pending, 'pendiente', 'pendientes')}<small>Se procesan al actualizar</small></div></div>`
    : '<span class="muted">Ninguno</span>';
  const md = st.done ? `<a class="icon-act" href="/markdown?${new URLSearchParams({project: s.project, category: s.category})}" target="_blank" rel="noopener" title="Abrir Markdown" aria-label="Abrir Markdown">${icon('doc')}</a>` : '';
  return `<tr>
    <td class="c-src first"><div class="src">${sourceThumb(s)}<div>
      <h3><a href="${safeUrl(s.url)}" target="_blank" rel="noopener noreferrer" title="${esc(s.url)}">${esc(label.main)}${label.sub ? ` · ${esc(label.sub)}` : ''}</a></h3>
      <p class="who">${icon(platIcon(s.platform), 'ic-xs')}<span>${esc(PLATFORM[s.platform] || s.platform)} · ${esc(p?.name || s.project)}</span></p>
      <div class="hover-acts">
        <button class="icon-act" data-sync="${esc(s.id)}" title="${single ? 'Procesar' : 'Actualizar'}" aria-label="${single ? 'Procesar' : 'Actualizar'} ${esc(label.main)}" ${lockAttr()}>${icon('refresh')}</button>
        ${st.review ? `<button class="icon-act" data-retry="${esc(s.id)}" title="Reintentar ${st.review}" aria-label="Reintentar ${esc(label.main)}" ${lockAttr()}>${icon('retry')}</button>` : ''}
        ${md}
        <a class="icon-act" href="${safeUrl(s.url)}" target="_blank" rel="noopener noreferrer" title="Abrir en ${esc(PLATFORM[s.platform] || 'la plataforma')}" aria-label="Abrir original">${icon('open')}</a>
        <button class="icon-act" data-source="${esc(s.id)}" title="Detalles y ajustes" aria-label="Detalles y ajustes de ${esc(label.main)}">${icon('more')}</button>
      </div>
    </div></div></td>
    <td class="c-follow"><div class="cell-icon">${icon(single ? 'play' : s.enabled ? 'eye' : 'eyeoff')}<div>${single ? 'Puntual' : s.enabled ? 'Activo' : 'Pausado'}</div></div></td>
    <td class="c-warn">${warn}</td>
    <td class="c-date" title="${esc(st.checked ? relative(st.checked) : '')}">${st.checked ? esc(fmtDate(st.checked)) : '—'}<span class="cell-sub">${st.checked ? 'Consultado' : 'Sin consultar'}</span></td>
    <td class="c-num r">${num(st.done)}</td>
    <td class="c-cov"><div class="cell-icon ${st.coverage === 'completa' && !single ? 'ok-text' : ''}">${icon(cIcon)}<div>${cLabel}<small>${esc(st.reason || cSub)}</small></div></div></td>
    <td class="c-prog last"><div class="prog"><span class="prog-v">${pct} %</span><span class="cell-sub">${plural(total, 'conocido', 'conocidos')}</span><div class="bar"><span data-w="${total ? st.done / total * 100 : 0}"></span><span class="rev" data-w="${total ? st.review / total * 100 : 0}"></span></div></div></td>
  </tr>`;
}
const SOURCE_HEAD = `<thead><tr><th class="c-src first">Fuente</th><th class="c-follow">Seguimiento</th><th class="c-warn">Avisos</th><th class="c-date sorted">Fecha ${icon('down')}</th><th class="c-num r">Procesados</th><th class="c-cov">Cobertura</th><th class="c-prog last">Progreso</th></tr></thead>`;
function videoRows(list, area, terms) {
  return list.map(v => `<tr data-open-video="${esc(area)}|${esc(v.id)}">
    <td class="v-main first"><div class="src">${thumb(v)}<div>
      <h3>${highlight(vtitle(v).slice(0, 200), terms)}</h3>
      <p class="excerpt">${highlight(excerptFor(v, terms), terms)}</p>
      <div class="hover-acts"><button class="icon-act" data-open-video="${esc(area)}|${esc(v.id)}" title="Leer transcripción" aria-label="Leer transcripción">${icon('doc')}</button><a class="icon-act" href="${safeUrl(v.url)}" target="_blank" rel="noopener noreferrer" title="Abrir original" aria-label="Abrir original">${icon('open')}</a></div>
    </div></div></td>
    <td class="v-person"><div class="cell-icon">${avatar(personById(v.person_id), 'avatar-sm')}<div>${esc(v.person)}</div></div></td>
    <td class="v-date">${esc(fmtDate(v.published_at))}<span class="cell-sub">Publicado</span></td>
    <td class="v-num r">${num(Array.isArray(v.segments) ? v.segments.length : v.segments)}</td>
    <td class="v-num r">${num(v.words)}</td>
    <td class="v-tags last">${(v.topics || []).map(x => `<span class="tag">${esc(TOPIC[x] || x)}</span>`).join('')}${(v.warnings || []).length ? `<span class="tag warn" title="${esc(v.warnings.join(' '))}">Revisar</span>` : ''}</td>
  </tr>`).join('');
}
const VIDEO_HEAD = `<thead><tr><th class="v-main first">Video</th><th class="v-person">Persona</th><th class="v-date sorted">Fecha ${icon('down')}</th><th class="v-num r">Fragmentos</th><th class="v-num r">Palabras</th><th class="v-tags last">Temas</th></tr></thead>`;
function pager(page, kind) {
  if (!page.total) return '';
  const from = page.offset + 1, to = page.offset + page.items.length;
  return `<div class="pager"><span>${num(from)}–${num(to)} de ${num(page.total)}</span><span><button class="round" data-page="${kind}|prev" aria-label="Página anterior" ${page.offset ? '' : 'disabled'}>${icon('left')}</button><button class="round" data-page="${kind}|next" aria-label="Página siguiente" ${page.hasMore ? '' : 'disabled'}>${icon('right')}</button></span></div>`;
}

function renderContenido() {
  const el = $('view-contenido');
  const sub = ['videos', 'revisar'].includes(state.route.sub) ? state.route.sub : 'fuentes';
  const {areas, people, sources} = state.catalog;
  const t = totals(sources);
  const totalVideos = ovAreas().reduce((acc, [, a]) => acc + (a.videos || 0), 0);
  const area = sub === 'videos' ? defaultArea() : state.content.area;
  const q = sub === 'videos' ? state.videos.q : state.content.q;
  const chips = (sub === 'videos' ? areas : [{id: '', name: 'Todas las áreas'}, ...areas]).map(a => `<button type="button" class="fchip" data-content-area="${esc(a.id)}" aria-pressed="${a.id === area}">${esc(a.name)}</button>`).join('');
  let body;
  if (sub === 'videos') {
    const vp = state.videos;
    const terms = fold(vp.q).split(/\s+/).filter(Boolean);
    body = vp.loading && !vp.items.length
      ? '<div class="empty"><span class="ring"></span><p>Cargando videos…</p></div>'
      : vp.items.length ? `<table class="table">${VIDEO_HEAD}<tbody>${videoRows(vp.items, vp.area, terms)}</tbody></table>${pager(vp, 'videos')}`
      : `<div class="empty">${icon('content')}<h3>${vp.q ? `Sin videos con «${esc(vp.q)}»` : 'Aún no hay videos en esta área'}</h3><p>${vp.q ? 'Prueba con otra palabra.' : 'Actualiza sus fuentes o reconstruye el índice.'}</p></div>`;
  } else {
    const query = fold(state.content.q.trim());
    const match = s => (!area || personById(s.person)?.area === area) && (!query || fold(`${personById(s.person)?.name} ${s.url} ${sourceLabel(s).main}`).includes(query));
    if (sub === 'revisar') {
      const list = sources.filter(s => stats(s).attention && match(s));
      body = `<div class="banner">${icon('info')}<span>Reintentar vuelve a descargar los videos fallidos. Si la plataforma los bloquea, usa «Importar texto» desde la persona.</span></div>`
        + (list.length ? `<table class="table">${SOURCE_HEAD}<tbody>${list.map(sourceRow).join('')}</tbody></table>` : `<div class="empty">${icon('check')}<h3>Nada por revisar</h3><p>Todas las fuentes respondieron y sus videos se procesaron.</p></div>`);
    } else {
      const groups = people.filter(p => !area || p.area === area).map(p => ({p, list: sourcesFor(p).filter(match)})).filter(g => g.list.length || !query);
      body = groups.length ? `<table class="table">${SOURCE_HEAD}<tbody>${groups.map(({p, list}) => {
        const g = totals(sourcesFor(p));
        return `<tr class="group"><td colspan="7"><div class="group-in">${avatar(p, 'avatar-sm')}<a href="#persona/${enc(p.id)}">${esc(p.name)}</a><span>${esc(areaName(p.area))} · ${plural(sourcesFor(p).length, 'fuente', 'fuentes')} · ${plural(g.done, 'procesado', 'procesados')}${g.review ? ` · <span class="warn-text">${num(g.review)} por revisar</span>` : ''}</span><button class="link-btn" data-add="${esc(p.id)}">${icon('add')}Añadir canal</button></div></td></tr>${list.map(sourceRow).join('')}`;
      }).join('')}</tbody></table>` : `<div class="empty">${icon('content')}<h3>${query ? 'Sin coincidencias' : 'Aún no hay fuentes'}</h3><p>${query ? 'Prueba con otro nombre, canal o enlace.' : 'Añade una persona con sus canales.'}</p><div class="actions"><button class="pill pill-solid" data-add="">${icon('person-add')}Añadir persona</button></div></div>`;
    }
  }
  el.innerHTML = `<div class="content-head">
      <div class="page-head"><h1 id="contenido-title">Contenido de la biblioteca</h1>
        <div class="actions"><button class="pill pill-line" data-sync-all ${lockAttr()}>${icon('refresh')}Actualizar todo</button><button class="pill pill-solid" data-add="">${icon('person-add')}Añadir persona</button></div></div>
      <nav class="tabs" aria-label="Secciones de contenido">
        <a href="#contenido" class="${sub === 'fuentes' ? 'on' : ''}">Fuentes<span class="n">${num(sources.length)}</span></a>
        <a href="#contenido/videos" class="${sub === 'videos' ? 'on' : ''}">Videos<span class="n">${totalVideos ? num(totalVideos) : ''}</span></a>
        <a href="#contenido/revisar" class="${sub === 'revisar' ? 'on' : ''}">Por revisar<span class="n">${t.attention ? num(t.attention) : ''}</span></a>
      </nav>
    </div>
    <div class="filterbar">${icon('filter')}${chips}<label class="sr-only" for="content-q">Filtrar</label><input id="content-q" type="search" value="${esc(q)}" placeholder="${sub === 'videos' ? 'Buscar en las transcripciones' : 'Filtrar por persona, canal o enlace'}" autocomplete="off"></div>
    ${body}`;
  applyWidths(el);
}
async function loadVideos(reset = false) {
  const vp = state.videos;
  const area = defaultArea();
  if (!area) return;
  if (reset) vp.offset = 0;
  vp.area = area;
  vp.loading = true;
  const key = `${area}|${vp.q}|${vp.offset}`;
  vp.key = key;
  if (state.route.view === 'contenido') keepFocus(renderContenido);
  try {
    const r = await api('/api/knowledge?' + new URLSearchParams({area, q: vp.q, offset: vp.offset}));
    if (vp.key !== key) return;
    Object.assign(vp, {items: r.videos, total: r.total || 0, hasMore: !!r.has_more, loading: false});
  } catch (e) { vp.loading = false; fail(e); }
  if (state.route.view === 'contenido' && state.route.sub === 'videos') keepFocus(renderContenido);
}

/* ---------- persona ---------- */
async function loadPerson(id, reset = true) {
  const p = personById(id);
  const pp = state.person;
  if (reset) Object.assign(pp, {q: pp.id === id ? pp.q : '', offset: 0, items: [], total: 0, hasMore: false});
  pp.id = id;
  if (!p) return;
  pp.loading = true;
  const key = `${id}|${pp.q}|${pp.offset}`;
  pp.key = key;
  try {
    const r = await api('/api/knowledge?' + new URLSearchParams({area: p.area, q: pp.q, person: id, offset: pp.offset}));
    if (pp.key !== key) return;
    Object.assign(pp, {items: r.videos, total: r.total || 0, hasMore: !!r.has_more, loading: false});
  } catch (e) { pp.loading = false; if (e.status !== 404) fail(e); }
  if (state.route.view === 'persona' && state.route.id === id) keepFocus(renderPersona);
}
function personChart(p) {
  const a = state.overview?.areas?.[p.area];
  const raw = Object.fromEntries(a?.months?.[p.id] || []);
  const keys = Object.keys(raw).sort();
  if (!keys.length) {
    return `<p class="chart-note">${state.overview?.partial ? 'Reinicia Creator MD para ver la evolución mensual.' : 'Sin fechas de publicación suficientes para el gráfico.'}</p>`;
  }
  const series = [];
  let [y, m] = keys[0].split('-').map(Number);
  const [ye, me] = keys.at(-1).split('-').map(Number);
  while (y < ye || (y === ye && m <= me)) {
    const k = `${y}-${String(m).padStart(2, '0')}`;
    series.push([k, raw[k] || 0]);
    if (++m > 12) { m = 1; y++; }
  }
  const W = 760, H = 250, L = 36, B = 26, T = 22;
  const max = Math.max(...series.map(s => s[1]), 1);
  const step = Math.pow(10, Math.floor(Math.log10(max)));
  const top = Math.ceil(max / step) * step;
  const x = i => L + (W - L - 10) * (series.length === 1 ? .5 : i / (series.length - 1));
  const yv = v => T + (H - T - B) * (1 - v / top);
  const pts = series.map((s, i) => [x(i), yv(s[1])]);
  const line = pts.map((pt, i) => `${i ? 'L' : 'M'}${pt[0].toFixed(1)} ${pt[1].toFixed(1)}`).join(' ');
  const area = `${line} L${pts.at(-1)[0].toFixed(1)} ${yv(0)} L${pts[0][0].toFixed(1)} ${yv(0)} Z`;
  const ticks = [0, .5, 1].map(f => Math.round(top * f));
  const peak = series.reduce((b, s, i) => s[1] > series[b][1] ? i : b, 0);
  const MES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const label = k => { const [yy, mm] = k.split('-'); return `${MES[+mm - 1]}${mm === '01' || k === series[0][0] ? ' ' + yy.slice(2) : ''}`; };
  const every = Math.max(1, Math.ceil(series.length / 8));
  const anchor = pts[peak][0] > W - 160 ? 'end' : 'start';
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Videos de ${esc(p.name)} por mes de publicación">
    ${ticks.map(v => `<line class="gl" x1="${L}" x2="${W}" y1="${yv(v)}" y2="${yv(v)}"/><text x="${L - 8}" y="${yv(v) + 4}" text-anchor="end">${v}</text>`).join('')}
    ${series.map((s, i) => i % every === 0 || i === series.length - 1 ? `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${label(s[0])}</text>` : '').join('')}
    <path class="area" d="${area}"/><path class="line" d="${line}"/>
    <circle class="pt" cx="${pts[peak][0]}" cy="${pts[peak][1]}" r="4.5"/>
    <text class="peak" x="${pts[peak][0] + (anchor === 'end' ? -10 : 10)}" y="${Math.max(14, pts[peak][1] - 8)}" text-anchor="${anchor}">${series[peak][1]} videos · ${label(series[peak][0])}</text>
  </svg>`;
}
function renderPersona() {
  const el = $('view-persona');
  const p = personById(state.route.id);
  if (!p) {
    el.innerHTML = `<div class="empty">${icon('person-add')}<h3 id="persona-title">Persona no encontrada</h3><p>Puede que se haya renombrado o eliminado.</p><div class="actions"><a class="pill pill-line" href="#panel">Volver al panel</a></div></div>`;
    return;
  }
  const tab = ['videos', 'fuentes'].includes(state.route.sub) ? state.route.sub : 'resumen';
  const list = sourcesFor(p);
  const t = totals(list);
  const pp = state.person;
  const base = `#persona/${enc(p.id)}`;
  const latest = pp.q ? null : pp.items[0];
  const lastVideo = (state.overview?.areas?.[p.area]?.latest || []).find(v => v.person_id === p.id) || latest;
  const platforms = [...new Set(list.map(s => `${PLATFORM[s.platform] || s.platform}${sourceLabel(s).sub ? ' ' + sourceLabel(s).sub : ''}`))].join(' · ');
  let body = '';
  if (tab === 'resumen') {
    const covered = list.filter(s => stats(s).coverage === 'completa').length;
    const checked = list.map(s => stats(s).checked).filter(Boolean).sort().at(-1);
    const recent = pp.q ? [] : pp.items.slice(0, 6);
    body = `<div class="wrap">
      <div class="stack">
        <section class="card analytics">
          <div class="an-head"><h2>Tu biblioteca tiene ${plural(t.done, 'video', 'videos')} de ${esc(p.name.split(' ')[0])}</h2></div>
          <div class="metrics">
            <div class="metric on"><span>Videos procesados</span><b>${num(t.done)}</b><small>en ${plural(list.length, 'fuente', 'fuentes')}</small></div>
            <div class="metric"><span>Por revisar</span><b>${num(t.review)}</b><small class="${t.review ? 'warn-text' : ''}">${t.review ? 'Reintenta o importa' : 'Nada pendiente'}</small></div>
            <div class="metric"><span>Cobertura completa</span><b>${covered} de ${list.length}</b><small>fuentes</small></div>
            <div class="metric"><span>Último video</span><b>${lastVideo ? esc(fmtDate(lastVideo.published_at).replace(/ de \d{4}$| \d{4}$/, '')) : '—'}</b><small>publicado</small></div>
          </div>
          <div class="chart">${personChart(p)}</div>
          <div class="an-foot"><a class="link-btn" href="${base}/videos">Ver todos sus videos</a></div>
        </section>
        <section class="card">
          <h2>Videos más recientes</h2>
          <p class="sub">Con transcripción y tiempos enlazados al original</p>
          ${pp.loading && !recent.length ? '<div class="empty"><span class="ring"></span></div>' : recent.length ? `<table class="top-table"><thead><tr><th class="rk"></th><th>Video</th><th class="r">Fragmentos</th><th class="r">Palabras</th></tr></thead>
          <tbody>${recent.map((v, i) => `<tr data-open-video="${esc(p.area)}|${esc(v.id)}"><td class="rk">${i + 1}</td><td><div class="vid">${thumb(v, 'thumb-md')}<span>${esc(vtitle(v))}</span></div></td><td class="r">${num(v.segments.length)}</td><td class="r">${num(v.words)}</td></tr>`).join('')}</tbody></table>`
          : '<p class="sub">Aún no hay videos procesados de esta persona.</p>'}
        </section>
      </div>
      <div class="stack">
        <section class="card">
          <h2>Fuentes</h2>
          <p class="sub">${checked ? `Última consulta ${esc(relative(checked))}` : 'Sin consultar todavía'}</p>
          <div>${list.map(s => {
            const st = stats(s);
            return `<button class="srow" data-source="${esc(s.id)}"><span class="pi">${icon(platIcon(s.platform))}</span>
              <span><b>${esc(PLATFORM[s.platform] || s.platform)}${sourceLabel(s).sub ? ' · ' + esc(sourceLabel(s).sub) : ''}</b><span class="s-sub ${st.error ? 'err-text' : ''}">${st.error ? esc(friendlyError(st.error, s.platform)) : `${esc((COVERAGE[st.coverage] || COVERAGE.desconocida)[1])} · ${esc(sourceLabel(s).main)}`}</span></span>
              <span class="val">${num(st.done)}${st.review ? `<small class="warn-text">${num(st.review)} revisar</small>` : st.pending ? `<small class="muted">${num(st.pending)} pendientes</small>` : '<small class="ok-text">al día</small>'}</span></button>`;
          }).join('') || '<p class="sub">Sin fuentes. Añade un canal.</p>'}</div>
          <div class="card-foot">${t.review ? `<a class="link-btn" href="${base}/fuentes">Reintentar ${plural(t.review, 'video', 'videos')}</a>` : ''}<button class="link-btn" data-add="${esc(p.id)}">Añadir canal</button></div>
        </section>
        ${latest ? `<section class="card">
          <h2>Del último video</h2>
          <p class="sub">${esc(vtitle(latest))}</p>
          <div class="quote">${latest.segments.slice(0, 4).map(s => `<p><span class="tc">${timecode(s.start)}</span> ${esc(s.text)}</p>`).join('')}</div>
          <div class="card-foot"><button class="link-btn" data-open-video="${esc(p.area)}|${esc(latest.id)}">Leer transcripción</button></div>
        </section>` : ''}
      </div>
    </div>`;
  } else if (tab === 'videos') {
    const terms = fold(pp.q).split(/\s+/).filter(Boolean);
    body = `<div class="card analytics">
      <div class="filterbar">${icon('search')}<label class="sr-only" for="person-q">Buscar en sus videos</label><input id="person-q" type="search" value="${esc(pp.q)}" placeholder="Buscar en las transcripciones de ${esc(p.name)}" autocomplete="off"></div>
      ${pp.loading && !pp.items.length ? '<div class="empty"><span class="ring"></span><p>Cargando videos…</p></div>'
        : pp.items.length ? `<table class="table">${VIDEO_HEAD}<tbody>${videoRows(pp.items, p.area, terms)}</tbody></table>${pager(pp, 'person')}`
        : `<div class="empty">${icon('content')}<h3>${pp.q ? `Sin videos con «${esc(pp.q)}»` : 'Aún no hay videos procesados'}</h3></div>`}
    </div>`;
  } else {
    body = `<div class="card analytics"><table class="table">${SOURCE_HEAD}<tbody>${list.map(sourceRow).join('')}</tbody></table></div>`;
  }
  el.innerHTML = `<div class="hero">${avatar(p, 'avatar-lg')}<div><h1 id="persona-title">${esc(p.name)}</h1><p>${esc(areaName(p.area))}${platforms ? ' · ' + esc(platforms) : ''}</p></div>
      <div class="actions"><button class="pill pill-line" data-import-person="${esc(p.id)}">${icon('paste')}Importar texto</button><button class="pill pill-line" data-add="${esc(p.id)}">${icon('add')}Añadir canal</button><button class="pill pill-solid" data-sync-person="${esc(p.id)}" ${lockAttr()}>${icon('refresh')}Actualizar fuentes</button></div></div>
    <nav class="tabs persona-tabs" aria-label="Secciones de la persona">
      <a href="${base}" class="${tab === 'resumen' ? 'on' : ''}">Resumen</a>
      <a href="${base}/videos" class="${tab === 'videos' ? 'on' : ''}">Videos<span class="n">${num(t.done)}</span></a>
      <a href="${base}/fuentes" class="${tab === 'fuentes' ? 'on' : ''}">Fuentes<span class="n">${num(list.length)}</span></a>
      <button type="button" data-knowledge="${esc(p.id)}">Conocimiento</button>
    </nav>
    ${body}`;
  applyWidths(el);
}

/* ---------- conocimiento ---------- */
function renderAreaSelect() {
  const select = $('knowledge-area');
  const previous = select.value;
  select.innerHTML = state.catalog.areas.map(a => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join('');
  const preferred = [previous, defaultArea(), state.catalog.areas[0]?.id].find(id => id && state.catalog.areas.some(a => a.id === id));
  select.value = preferred || '';
  updateSkillLink();
}
function updateSkillLink() {
  const area = $('knowledge-area').value;
  $('download-skill').href = '/skill?area=' + enc(area);
  $('download-skill').download = area + '-evidence.zip';
  $('download-skill').setAttribute('aria-disabled', String(!area));
}
function renderPersonFilters() {
  const area = $('knowledge-area').value;
  const people = state.catalog.people.filter(p => p.area === area);
  $('person-filters').innerHTML = people.length > 1
    ? [`<button type="button" class="fchip" data-person-filter="" aria-pressed="${!state.k.personFilter}">Todas las personas</button>`,
      ...people.map(p => `<button type="button" class="fchip" data-person-filter="${esc(p.id)}" aria-pressed="${state.k.personFilter === p.id}">${esc(p.name)}</button>`)].join('')
    : '';
}
const queryTerms = () => fold($('knowledge-query').value).split(/\s+/).filter(Boolean);
function highlight(text, terms) {
  text = String(text || '');
  if (!terms.length) return esc(text);
  let folded = '';
  const map = [];
  for (let i = 0; i < text.length; i++) {
    for (const ch of fold(text[i])) { folded += ch; map.push(i); }
  }
  const ranges = [];
  for (const term of terms) {
    let at = folded.indexOf(term);
    while (at !== -1) {
      ranges.push([map[at], map[at + term.length - 1] + 1]);
      at = folded.indexOf(term, at + term.length);
    }
  }
  if (!ranges.length) return esc(text);
  ranges.sort((a, b) => a[0] - b[0]);
  let out = '', last = 0;
  for (const [start, end] of ranges) {
    if (end <= last) continue;
    const from = Math.max(start, last);
    out += esc(text.slice(last, from)) + '<mark>' + esc(text.slice(from, end)) + '</mark>';
    last = end;
  }
  return out + esc(text.slice(last));
}
function excerptFor(card, terms) {
  const segments = Array.isArray(card.segments) ? card.segments : card.preview || [];
  if (!terms.length) return card.excerpt || segments.map(s => s.text).join(' ').slice(0, 300);
  const hit = segments.find(s => terms.some(t => fold(s.text).includes(t)));
  return hit ? hit.text : card.excerpt || '';
}
async function searchKnowledge(append = false) {
  const area = $('knowledge-area').value;
  const k = state.k;
  updateSkillLink();
  renderPersonFilters();
  if (!area) { Object.assign(k, {list: [], total: 0, insights: []}); renderKnowledge(); return; }
  const version = ++k.version;
  if (!append) $('knowledge-count').textContent = 'Buscando…';
  const r = await api('/api/knowledge?' + new URLSearchParams({area, q: $('knowledge-query').value, person: k.personFilter, offset: append ? k.list.length : 0}));
  if (version !== k.version) return;
  k.list = append ? [...k.list, ...r.videos] : r.videos;
  k.total = r.total || 0;
  k.hasMore = !!r.has_more;
  k.generatedAt = r.generated_at || '';
  k.insights = r.curated?.insights || [];
  k.reviewedAt = r.curated?.reviewed_at || '';
  let open = false;
  if (!append) {
    if (k.pending) { k.selected = k.pending; k.pending = null; open = k.selectedOpen; k.selectedOpen = false; }
    const there = k.selected && (k.selected.type === 'insight' ? k.insights.some(i => i.id === k.selected.id) : k.list.some(c => c.id === k.selected.id));
    if (!there) k.selected = null;
    if (!k.selected && matchMedia('(min-width: 1241px)').matches && k.list[0]) k.selected = {type: 'video', id: k.list[0].id};
  }
  renderKnowledge();
  if (open && k.selected) openReader(k.selected);
}
function renderKnowledge() {
  const area = $('knowledge-area').value;
  const k = state.k;
  const terms = queryTerms();
  const q = $('knowledge-query').value.trim();
  $('knowledge-sub').textContent = k.generatedAt ? `Índice de ${areaName(area)} · actualizado ${fmtDateTime(k.generatedAt)}` : 'Busca dentro de las transcripciones y abre el momento exacto del video.';
  $('build-knowledge').disabled = jobRunning() || !area;
  const person = k.personFilter ? personById(k.personFilter)?.name : '';
  $('knowledge-count').innerHTML = !area ? '' : `<b>${num(k.total)}</b> ${k.total === 1 ? 'video' : 'videos'}${q ? ` con «${esc(q)}»` : ''}${person ? ` de ${esc(person)}` : ''}`;
  const relevant = k.insights.filter(i => terms.every(t => fold(JSON.stringify(i)).includes(t)));
  const collapsed = !k.allInsights && relevant.length > 3;
  $('insights').innerHTML = relevant.length ? `<section class="card insights" aria-labelledby="ins-title">
      <h2 id="ins-title">${icon('spark')}Criterios revisados</h2>
      <div class="vlist">${relevant.slice(0, collapsed ? 3 : undefined).map(i => `<button class="ins" data-insight="${esc(i.id)}" ${k.selected?.type === 'insight' && k.selected.id === i.id ? 'aria-current="true"' : ''}>${icon('spark')}<span><b>${highlight(i.title, terms)}</b><small>${i.stale ? '<span class="warn-text">Revisar: cambió una fuente</span>' : plural(i.evidence.length, 'cita', 'citas')}</small></span></button>`).join('')}</div>
      ${relevant.length > 3 ? `<div class="card-foot"><button class="link-btn" data-toggle-insights>${collapsed ? `Ver los ${relevant.length} criterios` : 'Ver menos'}</button></div>` : ''}
    </section>` : '';
  if (!area) {
    $('knowledge-results').innerHTML = `<li class="empty">${icon('folder')}<h3>Crea un área primero</h3><p>El conocimiento se organiza por área.</p></li>`;
  } else if (!k.list.length) {
    $('knowledge-results').innerHTML = k.generatedAt || q
      ? `<li class="empty">${icon('search')}<h3>Sin resultados${q ? ` para «${esc(q)}»` : ''}</h3><p>Prueba con otra palabra o quita el filtro de persona. Todas las palabras deben aparecer en el mismo video.</p></li>`
      : `<li class="empty">${icon('bulb')}<h3>Aún no hay índice para ${esc(areaName(area))}</h3><p>Actualiza sus fuentes o reconstruye el índice con lo ya transcrito.</p><div class="actions"><button class="pill pill-solid" data-build>Reconstruir índice</button></div></li>`;
  } else {
    $('knowledge-results').innerHTML = k.list.map(c => `<li><button class="result" data-evidence="${esc(c.id)}" ${k.selected?.type === 'video' && k.selected.id === c.id ? 'aria-current="true"' : ''}>
      ${thumb(c)}
      <span><h3>${highlight(vtitle(c).slice(0, 200), terms)}</h3>
      <span class="meta">${esc(c.person)} · ${esc(fmtDate(c.published_at))}${c.warnings.length ? ' · <span class="warn-text">revisar</span>' : ''}${c.duplicate_of ? ' · duplicado' : ''}</span>
      <p>${highlight(excerptFor(c, terms), terms)}</p></span>
    </button></li>`).join('');
  }
  $('load-more').hidden = !k.hasMore;
  renderReader();
}
function renderReader() {
  const reader = $('reader');
  const k = state.k, sel = k.selected, terms = queryTerms();
  if (sel?.type === 'insight') {
    const i = k.insights.find(x => x.id === sel.id);
    if (!i) { k.selected = null; renderReader(); return; }
    reader.innerHTML = `<header class="reader-head"><div class="reader-top no-thumb"><div>
        <p class="reader-meta">${icon('spark', 'ic-xs')}Criterio revisado${k.reviewedAt ? ` · ${esc(fmtDate(k.reviewedAt))}` : ''}</p>
        <h2>${esc(i.title)}</h2></div><button class="round reader-close" data-close-reader aria-label="Cerrar">${icon('close')}</button></div></header>
      <div class="prose">
        <p class="lead">${highlight(i.principle, terms)}</p>
        ${i.stale ? `<p class="note note-warn">${icon('alert')}<span>Una de sus fuentes cambió desde la revisión. Comprueba la evidencia antes de aplicarlo.</span></p>` : ''}
        <h4>Cuándo aplica</h4><p>${esc(i.when)}</p>
        <h4>Aplicación propuesta</h4><ol>${i.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
        <h4>Límites y contraejemplos</h4><p>${esc(i.limits)}</p>
        <h4>Evidencia</h4><div class="ev-links">${i.evidence.map(e => `<a href="${safeUrl(e.url)}" target="_blank" rel="noopener noreferrer"><span class="tc">${timecode(e.start)}</span><span>${esc(e.person)} · hasta ${timecode(e.end)}</span></a>`).join('')}</div>
        ${(i.official || []).length ? `<h4>Documentación oficial</h4><div class="ev-links">${i.official.map(s => `<a href="${safeUrl(s.url)}" target="_blank" rel="noopener noreferrer">${icon('open', 'ic-xs')}<span>${esc(s.title)}</span></a>`).join('')}</div>` : ''}
        <p class="fineprint">La aplicación propuesta es una síntesis editorial de la biblioteca, no una garantía de resultados.</p>
      </div>`;
    return;
  }
  const c = sel?.type === 'video' ? k.list.find(x => x.id === sel.id) : null;
  if (!c) {
    reader.innerHTML = `<div class="reader-empty">${icon('content')}<b>Elige un video</b>Verás su transcripción completa con tiempos enlazados al original.</div>`;
    return;
  }
  const hits = c.segments.filter(s => terms.some(t => fold(s.text).includes(t)));
  const link = s => c.platform === 'youtube' ? c.url + (c.url.includes('?') ? '&' : '?') + 't=' + Math.floor(s.start) + 's' : c.url;
  const timed = c.segments.some(s => s.start > 0 || s.end > 0);
  reader.innerHTML = `<header class="reader-head">
      <div class="reader-top">${thumb(c)}<div>
        <h2>${esc(vtitle(c))}</h2>
        <p class="reader-meta">${icon(platIcon(c.platform), 'ic-xs')}${esc(c.person)} · ${esc(fmtDate(c.published_at))} · ${plural(c.segments.length, 'fragmento', 'fragmentos')} · ${num(c.words)} palabras</p></div>
        <button class="round reader-close" data-close-reader aria-label="Cerrar">${icon('close')}</button></div>
      <div class="reader-actions">
        <a class="pill pill-line pill-sm" href="${safeUrl(c.url)}" target="_blank" rel="noopener noreferrer">${icon('open')}Abrir video</a>
        <button class="pill pill-sm" data-copy-cite="${esc(c.id)}">${icon('copy')}Copiar cita</button>
        ${hits.length ? `<label class="switch-row"><input type="checkbox" role="switch" class="switch" id="only-hits" ${k.onlyHits ? 'checked' : ''}><span>Solo ${plural(hits.length, 'coincidencia', 'coincidencias')}</span></label>` : ''}
      </div>
      ${c.warnings.length ? `<p class="note note-warn">${icon('alert')}<span>${esc(c.warnings.join(' '))}</span></p>` : ''}
      <p class="reader-note">${METHOD[c.method] || 'Transcripción automática.'} Verifica cifras, nombres y lo que se muestra en pantalla antes de convertirlo en una recomendación.</p>
    </header>
    <ol class="transcript ${k.onlyHits && hits.length ? 'only-hits' : ''}">${c.segments.map(s => {
      const hit = terms.length && terms.some(t => fold(s.text).includes(t));
      return `<li class="${hit ? 'hit' : ''}">${timed ? `<a class="tc" href="${safeUrl(link(s))}" target="_blank" rel="noopener noreferrer" title="Abrir en ${timecode(s.start)}">${timecode(s.start)}</a>` : '<span class="tc">—</span>'}<p>${highlight(s.text, terms)}</p></li>`;
    }).join('')}</ol>`;
  const first = reader.querySelector('.transcript li.hit');
  reader.scrollTop = first ? Math.max(0, first.offsetTop - reader.querySelector('.reader-head').offsetHeight - 16) : 0;
}
function openReader(selection) {
  state.k.selected = selection;
  renderKnowledge();
  if (matchMedia('(max-width: 1240px)').matches) {
    $('reader').classList.add('open');
    document.body.style.overflow = 'hidden';
    $('reader').focus();
  }
}
function closeReader() {
  $('reader').classList.remove('open');
  document.body.style.overflow = '';
}
function openInKnowledge(area, selection) {
  const k = state.k;
  k.pending = selection;
  k.selectedOpen = true;
  k.personFilter = '';
  $('knowledge-query').value = '';
  renderAreaSelect();
  $('knowledge-area').value = area;
  if (state.route.view === 'conocimiento') searchKnowledge().catch(fail); else go('#conocimiento');
}

/* ---------- actividad ---------- */
function jobTarget(job) {
  if (!job) return '';
  if (['skill-build', 'skill-curation'].includes(job.action)) return skillsState.projects.find(p => p.id === job.project)?.name || job.project;
  if (job.action === 'knowledge-build') return 'Todas las áreas';
  const name = src => `${personById(src.person)?.name || src.project} · ${PLATFORM[src.platform] || src.platform}`;
  if (job.project === 'biblioteca' && job.category === 'sistema') {
    let src = null;
    if (job.status === 'running') src = state.catalog.sources.find(s => s.id === state.activeSource);
    else {
      const consulted = new Set((job.logs || []).map(l => /^Consultando \S+ · (.+)$/.exec(l.message || '')?.[1]).filter(Boolean));
      if (consulted.size === 1) src = state.catalog.sources.find(s => s.project === [...consulted][0]);
    }
    return src ? name(src) : 'Toda la biblioteca';
  }
  const src = state.catalog.sources.find(s => s.project === job.project && s.category === job.category);
  return src ? name(src) : job.project;
}
function jobSummary(job) {
  const r = job.result;
  if (['skill-build', 'skill-curation'].includes(job.action)) return 'El paquete conserva el estado de revisión de sus fuentes.';
  if (!r) return '';
  const parts = [];
  if (Array.isArray(r.sources)) {
    const errors = r.sources.filter(x => x.error).length;
    parts.push(`${plural(r.sources.length, 'fuente consultada', 'fuentes consultadas')}${errors ? `, ${errors} con error` : ''}.`);
  }
  if (Array.isArray(r.knowledge)) parts.push(r.knowledge.map(k => `${areaName(k.area)}: ${num(k.videos)} videos indexados`).join(' · ') + '.');
  if (r.kind === 'retry' || r.kind === 'recover-history') {
    const done = (r.completed_video_ids || []).length, failed = (r.failed_video_ids || []).length;
    parts.push(`${plural(done, 'video procesado', 'videos procesados')}${failed ? `, ${failed} siguen fallando` : ''}.`);
  }
  return parts.join(' ');
}
async function loadActivity() {
  const {jobs} = await api('/api/jobs');
  adoptRunningJob(jobs);
  const el = $('view-actividad');
  const t = totals(state.catalog.sources);
  el.innerHTML = `<div class="page-head"><div><h1 id="actividad-title">Actividad</h1><p class="page-sub">Cada video terminado se guarda al momento, aunque cierres esta ventana.</p></div></div>
    <div id="activity-current"></div>
    ${t.attention ? `<section class="card current"><div class="current-head"><span class="warn-text">${icon('alert')}</span><h2>${plural(t.attention, 'fuente con avisos', 'fuentes con avisos')}</h2></div><p class="sub">${plural(t.review, 'video por revisar', 'videos por revisar')}${t.errors ? ` · ${plural(t.errors, 'fuente sin respuesta', 'fuentes sin respuesta')}` : ''}.</p><div><a class="link-btn" href="#contenido/revisar">Ver en Contenido</a></div></section>` : ''}
    <section class="card jobs" aria-label="Historial de tareas">
      <div class="jobs-head"><span>Estado</span><span>Tarea</span><span>Fecha</span><span></span></div>
      ${jobs.length ? jobs.map(j => {
        const [label, tone, ic] = JOB_STATUS[j.status] || [j.status, 'warn', 'info'];
        const summary = jobSummary(j);
        return `<details class="job" ${j.status === 'running' ? 'open' : ''}>
          <summary><span class="status st-${tone}">${icon(ic)}${esc(label)}</span><span class="job-name"><b>${esc(ACTIONS[j.action] || j.action)}</b> · ${esc(jobTarget(j))}</span><time datetime="${esc(j.created_at)}">${esc(fmtDateTime(j.created_at))}</time>${icon('caret')}</summary>
          <div class="job-body">
            ${j.error ? `<p class="note note-err">${icon('alert')}<span>${esc(friendlyError(j.error))}</span></p>` : ''}
            ${summary ? `<p>${esc(summary)}</p>` : ''}
            <pre class="log">${esc((j.logs || []).map(l => `${l.time}  ${l.message}`).join('\n'))}</pre>
          </div></details>`;
      }).join('') : `<div class="empty">${icon('history')}<h3>Sin tareas todavía</h3><p>Las actualizaciones y reintentos aparecerán aquí.</p></div>`}
    </section>`;
  renderCurrent();
}
function renderCurrent() {
  const box = $('activity-current');
  if (!box) return;
  const job = state.job;
  if (!jobRunning() || !job) { box.innerHTML = ''; return; }
  const percent = Math.max(0, Math.min(100, Number(job.percent) || 0));
  const logs = (job.logs || []).slice(-6).map(l => `${l.time || ''}  ${l.message}`).join('\n');
  box.innerHTML = `<section class="card current" role="status">
    <div class="current-head"><span class="ring st-run"></span><h2>${esc(ACTIONS[job.action] || 'Tarea')} · ${esc(jobTarget(job))}</h2><span class="pct">${percent} %</span></div>
    <div class="bar"><span data-w="${percent}"></span></div>
    <p class="sub">${job.total ? `${num(job.processed)} de ${num(job.total)} · ` : ''}${esc(job.logs?.at(-1)?.message || 'Preparando…')}${state.queue.length ? ` · ${plural(state.queue.length, 'fuente más en cola', 'fuentes más en cola')}` : ''}</p>
    ${logs ? `<pre class="log">${esc(logs)}</pre>` : ''}
  </section>`;
  applyWidths(box);
}

/* ---------- tareas ---------- */
function saveQueue() {
  store.set('creator-md-queue', state.queue.length ? JSON.stringify(state.queue) : null);
  store.set('creator-md-queue-total', state.queue.length ? String(state.queueTotal) : null);
}
// Sigue también las tareas lanzadas por la programación o desde otra pestaña.
function adoptRunningJob(jobs) {
  if (state.activeJob) return;
  const active = (jobs || []).find(job => job.status === 'running' && job.id);
  if (!active) return;
  state.activeJob = active.id;
  state.job = active;
  state.activeSource = state.catalog.sources.find(s => s.project === active.project && s.category === active.category)?.id || '';
  store.set('creator-md-active-job', state.activeJob);
  store.set('creator-md-active-source', state.activeSource || null);
  renderView();
  pollJob();
}
async function startJob(action, payload = {}, trigger) {
  if (jobRunning()) { snack('Ya hay una tarea en curso. Espera a que termine o revisa Actividad.', 'info'); return; }
  if (trigger) { trigger.disabled = true; trigger.classList.add('is-busy'); }
  try {
    const result = await api('/api/' + action, action.startsWith('skills/') ? payload : {project: 'biblioteca', category: 'sistema', ...payload});
    state.activeJob = result.job_id;
    state.activeSource = payload.source_id || payload.retry_source || '';
    const skillRoute = /^skills\/([^/]+)\/(build|curation)$/.exec(action);
    const skillId = skillRoute?.[1];
    state.job = {action: skillRoute ? 'skill-' + skillRoute[2] : action, percent: 0, logs: [{message: 'Tarea preparada'}], status: 'running', project: skillId || payload.project || 'biblioteca', category: skillId ? 'skills' : payload.category || 'sistema'};
    store.set('creator-md-active-job', state.activeJob);
    store.set('creator-md-active-source', state.activeSource || null);
    renderView();
    pollJob();
  } finally {
    if (trigger && trigger.isConnected) { trigger.disabled = false; trigger.classList.remove('is-busy'); }
  }
}
function syncPerson(id, trigger) {
  const p = personById(id);
  const ids = sourcesFor(p).filter(s => s.enabled || s.kind === 'single_video').map(s => s.id);
  if (!ids.length) { snack('Esta persona no tiene fuentes con seguimiento activo.', 'info'); return; }
  state.queue = ids.slice(1);
  state.queueTotal = ids.length;
  saveQueue();
  startJob('library-sync', {source_id: ids[0]}, trigger).catch(e => { state.queue = []; saveQueue(); fail(e); });
}
let pollTimer;
async function pollJob() {
  clearTimeout(pollTimer);
  if (!state.activeJob) return;
  try {
    const job = await api('/api/job?id=' + enc(state.activeJob));
    state.job = job;
    renderJobUI();
    if (['completed', 'failed', 'interrupted'].includes(job.status)) {
      finishJob();
      const nextId = job.status !== 'interrupted' ? state.queue.shift() : null;
      if (!nextId) { state.queue = []; state.queueTotal = 0; }
      saveQueue();
      if (job.status === 'completed') snack(`${ACTIONS[job.action] || 'Tarea'} terminada. ${jobSummary(job) || 'Revisa la cobertura de cada fuente.'}`);
      else snack(friendlyError(job.error) || 'La tarea se interrumpió. Lo terminado se conservó.', 'error');
      await refresh().catch(() => {});
      loadOverview().catch(() => {});
      if (state.route.view === 'persona') loadPerson(state.route.id, false);
      if (state.route.view === 'conocimiento') searchKnowledge().catch(() => {});
      if (state.route.view === 'actividad') loadActivity().catch(() => {});
      if (state.route.view === 'skills' && job.status === 'completed') loadSkills().catch(fail);
      if (state.route.view === 'skills' && job.status === 'failed' && job.action === 'skill-curation' && $('skill-curation-error')) $('skill-curation-error').textContent = job.error || 'No se pudo validar la síntesis.';
      renderView();
      if (nextId) startJob('library-sync', {source_id: nextId}).catch(fail);
      return;
    }
    if (state.route.view === 'actividad') renderCurrent();
  } catch (e) {
    if (e.status === 404) {
      finishJob();
      state.queue = []; saveQueue();
      renderView();
      snack('La tarea guardada ya no existe. Consulta la biblioteca para continuar.', 'info');
      return;
    }
    $('dock-message').textContent = 'Reconectando con la aplicación…';
  }
  pollTimer = setTimeout(pollJob, 2000);
}
function finishJob() {
  state.activeJob = null;
  state.activeSource = '';
  store.set('creator-md-active-job', null);
  store.set('creator-md-active-source', null);
  renderJobUI();
}
function renderJobUI() {
  const job = state.job;
  const running = jobRunning() && job;
  const percent = running ? Math.max(0, Math.min(100, Number(job.percent) || 0)) : 0;
  $('job-pill').hidden = !running;
  $('nav-activity').textContent = running ? String(1 + state.queue.length) : '';
  if (!running) { $('job-dock').hidden = true; return; }
  $('job-pill-text').textContent = `${percent} %`;
  $('job-pill').title = `${ACTIONS[job.action] || 'Tarea'} en curso`;
  const step = state.queueTotal > 1 ? ` · ${state.queueTotal - state.queue.length} de ${state.queueTotal}` : '';
  $('dock-title').textContent = `${ACTIONS[job.action] || 'Tarea'} en curso${step}`;
  $('dock-target').textContent = jobTarget(job);
  $('dock-message').textContent = job.logs?.at(-1)?.message || 'Preparando…';
  $('dock-pct').textContent = `${percent} %`;
  $('dock-bar').style.width = `${percent}%`;
  if (!$('dock-icon').firstChild) $('dock-icon').innerHTML = icon('refresh');
  $('job-dock').hidden = state.route.view === 'actividad';
}

/* ---------- configuración ---------- */
function fillSettings() {
  const s = state.catalog.settings;
  $('schedule-enabled').checked = !!s.enabled;
  const hours = Number(s.interval_hours || 24);
  if (![...document.querySelectorAll('input[name="interval"]')].some(r => Number(r.value) === hours)) {
    $('interval').insertAdjacentHTML('beforeend', `<label><input type="radio" name="interval" value="${hours}"><span>${hours} h</span></label>`);
  }
  document.querySelectorAll('input[name="interval"]').forEach(r => { r.checked = Number(r.value) === hours; });
  $('process-limit').value = s.process_limit || 50;
  document.querySelectorAll('input[name="asr-model"]').forEach(r => { r.checked = r.value === (s.model || 'base'); });
  $('allow-paid').checked = !!s.allow_paid;
}
function renderApify() {
  $('apify-status').textContent = state.apifyConfigured
    ? 'Hay un token guardado en Windows. Solo se usa si permites consultas de pago.'
    : 'Sin conexión. Puedes trabajar solo con fuentes públicas gratuitas.';
  $('apify-remove').hidden = !state.apifyConfigured;
}
const DEPS = {'yt-dlp': 'Listados, subtítulos y audio', ffmpeg: 'Conversión de audio', 'faster-whisper': 'Transcripción local', whisper: 'Whisper clásico', summarizer: 'Motor heredado'};
function renderDependencies(deps) {
  $('dependencies').innerHTML = Object.entries(deps).map(([name, d]) => {
    const cls = d.available ? 'ok' : d.optional ? 'opt' : 'missing';
    const status = d.available ? 'Disponible' : d.optional ? 'Opcional, no instalado' : 'Falta instalar';
    return `<li class="${cls}">${icon(d.available ? 'check' : d.optional ? 'minus' : 'xcircle')}<span><b>${esc(DEPS[name] || name)}</b> · ${status}</span><code>${esc(name)}</code></li>`;
  }).join('');
}
function settingsTab(tab) {
  document.querySelectorAll('[data-settings-tab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.settingsTab === tab)));
  document.querySelectorAll('#settings-dialog [data-pane]').forEach(p => { p.hidden = p.dataset.pane !== tab; });
  $('settings-save').hidden = tab === 'system';
}
function openSettings() {
  fillSettings();
  settingsTab('general');
  $('settings-state').textContent = '';
  if (!$('settings-dialog').open) $('settings-dialog').showModal();
}

/* ---------- diálogos ---------- */
function addPerson(personId, areaId) {
  const person = personById(personId);
  const area = state.catalog.areas.find(a => a.id === (person?.area || areaId || (state.route.view === 'persona' ? personById(state.route.id)?.area : '')));
  $('add-form').reset();
  $('add-error').textContent = '';
  $('add-detected').innerHTML = '';
  $('add-area').value = area?.name || (state.catalog.areas.length === 1 ? state.catalog.areas[0].name : '');
  $('add-name').value = person?.name || '';
  $('add-title').textContent = person ? `Añadir canal a ${person.name}` : 'Añadir persona';
  $('add-dialog').showModal();
  (person ? $('add-urls') : $('add-area').value ? $('add-name') : $('add-area')).focus();
}
function openImport(personId) {
  const people = state.catalog.people;
  if (!people.length) { snack('Primero añade una persona.', 'info'); return; }
  $('import-form').reset();
  $('import-error').textContent = '';
  $('import-person').innerHTML = people.map(p => `<option value="${esc(p.id)}">${esc(p.name)} · ${esc(areaName(p.area))}</option>`).join('');
  $('import-person').value = personId || people[0].id;
  $('import-person-field').hidden = !!personId;
  $('import-heading').textContent = personId ? `Importar transcripción · ${personById(personId)?.name || ''}` : 'Importar transcripción';
  $('import-dialog').showModal();
  (personId ? $('import-url') : $('import-person')).focus();
}
function openArea() {
  $('area-form').reset();
  $('area-error').textContent = '';
  $('area-dialog').showModal();
  $('area-name').focus();
}
function detectUrl(raw) {
  let url;
  try { url = new URL(raw); } catch { return {ok: false, text: `No es un enlace válido: ${raw}`}; }
  const host = url.hostname.replace(/^www\.|^m\./, '');
  const platform = /youtube\.com$|youtu\.be$/.test(host) ? 'youtube' : /tiktok\.com$/.test(host) ? 'tiktok' : /instagram\.com$/.test(host) ? 'instagram' : '';
  if (!platform) return {ok: false, text: `Plataforma no compatible: ${host}`};
  const video = /\/watch|^\/shorts\/[\w-]{6,}|\/video\/|\/reel\/|\/p\/|^\/live\//.test(url.pathname) || host === 'youtu.be';
  return {ok: true, platform, text: `${PLATFORM[platform]} · ${video ? 'video individual' : 'perfil'} · ${url.pathname.replace(/\/$/, '') || '/'}`};
}
function renderDetected() {
  const lines = $('add-urls').value.split(/\n/).map(s => s.trim()).filter(Boolean).slice(0, 12);
  $('add-detected').innerHTML = lines.map(line => {
    const d = detectUrl(line);
    return `<li class="${d.ok ? '' : 'bad'}">${icon(d.ok ? d.platform : 'alert')}<span>${esc(d.text)}</span></li>`;
  }).join('');
}
function openSource(id) {
  const s = state.catalog.sources.find(x => x.id === id);
  if (!s) return;
  const st = stats(s), label = sourceLabel(s), single = s.kind === 'single_video';
  state.currentSource = s.id;
  $('source-title').textContent = `${PLATFORM[s.platform] || s.platform} · ${label.main}${label.sub ? ' · ' + label.sub : ''}`;
  $('source-url').textContent = s.url;
  $('source-facts').innerHTML = [
    ['Persona', personById(s.person)?.name || s.project],
    ['Procesados', `${num(st.done)}${st.review ? ` · ${num(st.review)} por revisar` : ''}${st.pending ? ` · ${num(st.pending)} pendientes` : ''}`],
    ['Cobertura', `${(COVERAGE[st.coverage] || COVERAGE.desconocida)[1]}${st.reason ? ` — ${st.reason}` : ''}`],
    ['Última consulta', st.checked ? `${fmtDateTime(st.checked)} (${relative(st.checked)})` : 'Nunca'],
    ['Último listado completo', s.status?.last_complete_listing_at ? `${fmtDateTime(s.status.last_complete_listing_at)} · ${num(s.status.last_complete_listing_total)} publicaciones` : 'Sin acreditar'],
    ['Próxima', s.enabled && s.next_run_at ? `${fmtDateTime(s.next_run_at)} (${relative(s.next_run_at)})` : '—'],
    ['Carpeta', `${s.category}/${s.project}`],
  ].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  $('source-md').href = '/markdown?' + new URLSearchParams({project: s.project, category: s.category});
  $('source-md').hidden = !st.done;
  $('source-enabled').checked = !!s.enabled;
  $('source-enabled').disabled = single;
  $('source-enabled-hint').textContent = single ? 'Los videos sueltos se procesan una vez y no entran en las actualizaciones.' : 'Se consulta en «Actualizar todo» y en la programación.';
  $('source-limit').value = s.scan_limit;
  $('source-history-box').hidden = single;
  $('source-history').disabled = jobRunning();
  $('source-error').textContent = '';
  $('source-dialog').showModal();
}
async function copyCitation(id) {
  const c = state.k.list.find(x => x.id === id);
  if (!c) return;
  const text = `${c.person} — «${c.title}» (${fmtDate(c.published_at)}). ${c.url}`;
  try { await navigator.clipboard.writeText(text); snack('Cita copiada al portapapeles.'); }
  catch { snack('No se pudo copiar. Selecciona el texto manualmente.', 'error'); }
}
function submitting(form, busy) {
  form.querySelectorAll('button:not(.close-dialog)').forEach(b => { b.disabled = busy; });
}
function closeMenu() {
  $('create-menu').hidden = true;
  $('create-btn').setAttribute('aria-expanded', 'false');
}

/* ---------- eventos ---------- */
document.addEventListener('submit', event => {
  if (event.target.id === 'skill-project-form') {
    event.preventDefault();
    saveSkillProject(event.target, event.submitter?.value === 'build');
  }
  if (event.target.id === 'skill-curation-form') {
    event.preventDefault();
    saveSkillCuration(event.target);
  }
});
document.addEventListener('click', event => {
  const row = event.target.closest('tr[data-open-video]');
  const el = event.target.closest('button, a');
  if (!event.target.closest('.menu-wrap')) closeMenu();
  if (row && (!el || el.dataset.openVideo)) {
    const [area, id] = row.dataset.openVideo.split('|');
    openInKnowledge(area, {type: 'video', id});
    return;
  }
  if (!el) return;
  const d = el.dataset;
  if (el.hasAttribute('data-copy-review')) {
    navigator.clipboard.writeText($('skill-review-request').value).then(() => snack('Petición copiada.')).catch(() => {
      $('skill-review-request').focus(); $('skill-review-request').select(); snack('Seleccioné la petición. Puedes copiarla con Ctrl+C.', 'info');
    });
  }
  if (d.openVideo) { const [area, id] = d.openVideo.split('|'); openInKnowledge(area, {type: 'video', id}); return; }
  if (d.openInsight) { const [area, id] = d.openInsight.split('|'); openInKnowledge(area, {type: 'insight', id}); return; }
  if (el.hasAttribute('data-add')) { closeMenu(); addPerson(d.add); }
  if (d.addArea) addPerson('', d.addArea);
  if (el.hasAttribute('data-new-area')) { closeMenu(); openArea(); }
  if (el.hasAttribute('data-import-any')) { closeMenu(); openImport(''); }
  if (d.importPerson) openImport(d.importPerson);
  if (el.hasAttribute('data-sync-all')) startJob('library-sync', {}, el).catch(fail);
  if (d.syncPerson) syncPerson(d.syncPerson, el);
  if (el.hasAttribute('data-build')) startJob('knowledge-build', {}, el).catch(fail);
  if (d.sync) startJob('library-sync', {source_id: d.sync}, el).catch(fail);
  if (d.retry) {
    const s = state.catalog.sources.find(x => x.id === d.retry);
    if (s) startJob('retry', {project: s.project, category: s.category, count: 1000, retry_source: s.id}, el).catch(fail);
  }
  if (d.source) openSource(d.source);
  if (el.hasAttribute('data-open-settings')) openSettings();
  if (d.settingsTab) settingsTab(d.settingsTab);
  if (d.knowledge) {
    const person = personById(d.knowledge);
    state.k.personFilter = person.id;
    state.k.selected = null;
    $('knowledge-query').value = '';
    renderAreaSelect();
    $('knowledge-area').value = person.area;
    go('#conocimiento');
  }
  if (el.hasAttribute('data-content-area')) {
    state.content.area = d.contentArea;
    if (state.route.sub === 'videos') { state.videos.items = []; loadVideos(true); } else renderContenido();
  }
  if (d.page) {
    const [kind, dir] = d.page.split('|');
    const page = kind === 'videos' ? state.videos : state.person;
    page.offset = Math.max(0, page.offset + (dir === 'next' ? 60 : -60));
    if (kind === 'videos') loadVideos(); else loadPerson(state.person.id, false);
    window.scrollTo(0, 0);
  }
  if (d.evidence) openReader({type: 'video', id: d.evidence});
  if (d.insight) openReader({type: 'insight', id: d.insight});
  if (el.hasAttribute('data-close-reader')) closeReader();
  if (el.hasAttribute('data-person-filter')) { state.k.personFilter = d.personFilter; state.k.selected = null; searchKnowledge().catch(fail); }
  if (d.copyCite) copyCitation(d.copyCite);
  if (el.hasAttribute('data-toggle-insights')) { state.k.allInsights = !state.k.allInsights; renderKnowledge(); }
  if (el.classList.contains('close-dialog')) el.closest('dialog').close();
});
document.querySelectorAll('dialog').forEach(dialog => {
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
});
document.addEventListener('change', event => {
  if (event.target.id === 'only-hits') { state.k.onlyHits = event.target.checked; renderReader(); }
});
let inputTimer;
document.addEventListener('input', event => {
  const id = event.target.id;
  if (id === 'content-q') {
    clearTimeout(inputTimer);
    if (state.route.sub === 'videos') {
      state.videos.q = event.target.value;
      inputTimer = setTimeout(() => loadVideos(true), 400);
    } else {
      state.content.q = event.target.value;
      keepFocus(renderContenido);
    }
  }
  if (id === 'person-q') {
    clearTimeout(inputTimer);
    state.person.q = event.target.value;
    inputTimer = setTimeout(() => { state.person.offset = 0; loadPerson(state.person.id, false); }, 400);
  }
  if (id === 'knowledge-query') {
    clearTimeout(inputTimer);
    inputTimer = setTimeout(() => { state.k.selected = null; searchKnowledge().catch(fail); }, 400);
  }
  if (id === 'add-urls') renderDetected();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    if (!$('create-menu').hidden) { closeMenu(); $('create-btn').focus(); return; }
    if ($('reader').classList.contains('open')) { closeReader(); return; }
    if (document.body.classList.contains('side-open') && matchMedia('(max-width: 1100px)').matches) { setSide(false); return; }
  }
  if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.querySelector('dialog[open]')) return;
  event.preventDefault();
  const target = state.route.view === 'conocimiento' ? $('knowledge-query') : $('global-query');
  target.focus();
  target.select();
});
window.addEventListener('hashchange', route);

$('menu-toggle').onclick = () => {
  if (matchMedia('(max-width: 1100px)').matches) {
    setSide(!document.body.classList.contains('side-open'));
  } else {
    const mini = !document.body.classList.contains('side-mini');
    document.body.classList.toggle('side-mini', mini);
    store.set('creator-md-side', mini ? 'mini' : null);
    setSide(false);
  }
};
$('scrim').onclick = () => setSide(false);
$('create-btn').onclick = () => {
  const open = $('create-menu').hidden;
  $('create-menu').hidden = !open;
  $('create-btn').setAttribute('aria-expanded', String(open));
  if (open) $('create-menu').querySelector('button').focus();
};
$('job-pill').onclick = () => go('#actividad');
$('dock-toggle').onclick = () => {
  const collapsed = $('job-dock').classList.toggle('collapsed');
  $('dock-toggle').setAttribute('aria-expanded', String(!collapsed));
  $('dock-toggle').setAttribute('aria-label', collapsed ? 'Expandir' : 'Contraer');
};
$('open-settings').onclick = openSettings;
$('global-search').onsubmit = event => {
  event.preventDefault();
  const q = $('global-query').value.trim();
  state.k.personFilter = '';
  state.k.selected = null;
  $('knowledge-query').value = q;
  if (state.route.view === 'conocimiento') searchKnowledge().catch(fail); else go('#conocimiento');
  $('global-query').blur();
};
$('knowledge-search').onsubmit = event => { event.preventDefault(); clearTimeout(inputTimer); state.k.selected = null; searchKnowledge().catch(fail); };
$('knowledge-area').onchange = () => { state.k.personFilter = ''; state.k.selected = null; searchKnowledge().catch(fail); };
$('build-knowledge').onclick = event => startJob('knowledge-build', {}, event.currentTarget).catch(fail);
$('load-more').onclick = async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try { await searchKnowledge(true); } catch (e) { fail(e); } finally { button.disabled = false; }
};
$('download-skill').addEventListener('click', event => {
  if (!$('knowledge-area').value) { event.preventDefault(); return; }
  if (!state.k.generatedAt) { event.preventDefault(); snack('Primero construye el índice de esta área.', 'info'); }
});
$('source-history').onclick = () => {
  const s = state.catalog.sources.find(x => x.id === state.currentSource);
  if (!s) return;
  $('source-dialog').close();
  startJob('recover-history', {project: s.project, category: s.category, count: 1000, scan_limit: 10000, source_id: s.id}).catch(fail);
};

$('area-form').onsubmit = async event => {
  event.preventDefault();
  submitting(event.target, true);
  try {
    const result = await api('/api/library/area', {name: $('area-name').value});
    $('area-dialog').close();
    await refresh();
    snack(`Área «${result.name}» creada. Añade su primera persona cuando quieras.`);
    addPerson('', result.id);
  } catch (e) { $('area-error').textContent = e.message; } finally { submitting(event.target, false); }
};
$('add-form').onsubmit = async event => {
  event.preventDefault();
  submitting(event.target, true);
  try {
    const urls = $('add-urls').value.split(/\n/).map(s => s.trim()).filter(Boolean);
    const result = await api('/api/library/add', {area: $('add-area').value, person: $('add-name').value, urls});
    $('add-dialog').close();
    await refresh();
    snack(`${plural(result.sources.length, 'fuente guardada', 'fuentes guardadas')}. Pulsa Actualizar fuentes para recopilar sus videos.`);
    if (state.route.view === 'skills' && $('skill-project-form')) {
      const selected = new Set(new FormData($('skill-project-form')).getAll('person_ids'));
      if (result.person) selected.add(result.person);
      document.querySelector('#skill-project-form .skill-people').innerHTML = skillPeopleHTML(selected);
    } else if (result.person) go(`#persona/${enc(result.person)}`);
  } catch (e) { $('add-error').textContent = e.message; } finally { submitting(event.target, false); }
};
$('source-form').onsubmit = async event => {
  event.preventDefault();
  submitting(event.target, true);
  try {
    await api('/api/library/source', {id: state.currentSource, enabled: $('source-enabled').checked, scan_limit: Number($('source-limit').value)});
    $('source-dialog').close();
    await refresh();
    snack('Fuente actualizada.');
  } catch (e) { $('source-error').textContent = e.message; } finally { submitting(event.target, false); }
};
$('import-form').onsubmit = async event => {
  event.preventDefault();
  submitting(event.target, true);
  try {
    await api('/api/library/import', {person_id: $('import-person').value, url: $('import-url').value, title: $('import-title').value, text: $('import-text').value});
    $('import-dialog').close();
    await refresh();
    loadOverview().catch(() => {});
    snack('Transcripción guardada con su fuente e incorporada al conocimiento.');
  } catch (e) { $('import-error').textContent = e.message; } finally { submitting(event.target, false); }
};
$('settings-form').onsubmit = async event => {
  event.preventDefault();
  submitting(event.target, true);
  $('settings-save').disabled = true;
  try {
    await api('/api/library/settings', {
      enabled: $('schedule-enabled').checked,
      interval_hours: Number(document.querySelector('input[name="interval"]:checked')?.value || 24),
      process_limit: Number($('process-limit').value),
      model: document.querySelector('input[name="asr-model"]:checked')?.value || 'base',
      allow_paid: $('allow-paid').checked,
    });
    await refresh();
    $('settings-state').textContent = 'Guardado a las ' + new Date().toLocaleTimeString('es-PE', {hour: '2-digit', minute: '2-digit'});
    snack('Configuración guardada.');
  } catch (e) { fail(e); } finally { submitting(event.target, false); $('settings-save').disabled = false; }
};
$('apify-form').onsubmit = async event => {
  event.preventDefault();
  submitting(event.target, true);
  try {
    await api('/api/settings/apify', {token: $('apify-token').value});
    $('apify-token').value = '';
    state.apifyConfigured = true;
    renderApify();
    snack('Conexión guardada en Windows.');
  } catch (e) { fail(e); } finally { submitting(event.target, false); }
};
$('apify-remove').onclick = async () => {
  if (!confirm('¿Quitar el token de Apify guardado en este equipo?')) return;
  try {
    await api('/api/settings/apify', undefined, 'DELETE');
    state.apifyConfigured = false;
    renderApify();
    snack('Conexión eliminada.');
  } catch (e) { fail(e); }
};

/* ---------- datos ---------- */
function applyCatalog(catalog) {
  const key = JSON.stringify(catalog);
  if (key === state.catalogKey) return false;
  state.catalogKey = key;
  state.catalog = catalog;
  state.loaded = true;
  return true;
}
async function refresh() {
  const [catalog, recent] = await Promise.all([api('/api/library'), api('/api/jobs').catch(() => ({jobs: []}))]);
  const changed = applyCatalog(catalog);
  adoptRunningJob(recent.jobs);
  if (changed) {
    renderSide();
    if (['panel', 'contenido', 'persona'].includes(state.route.view)) keepFocus(() => renderView());
    if (state.route.view === 'conocimiento') renderPersonFilters();
  }
  return changed;
}

/* ---------- inicio ---------- */
(async () => {
  hydrateIcons();
  if (matchMedia('(hover: none)').matches) document.body.classList.add('touch');
  if (store.get('creator-md-side') === 'mini') document.body.classList.add('side-mini');
  try {
    const data = await api('/api/bootstrap');
    applyCatalog(data.catalog);
    state.apifyConfigured = !!data.integrations?.apify?.configured;
    renderApify();
    renderDependencies(data.dependencies || {});
    route();
    loadOverview().catch(() => { state.overview = {areas: {}, partial: true}; renderView(); });
    if (state.activeJob) pollJob();
    else api('/api/jobs').then(r => adoptRunningJob(r.jobs)).catch(() => {});
    setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 30000);
    setInterval(() => { if (!document.hidden && !jobRunning()) loadOverview().catch(() => {}); }, 300000);
  } catch (e) {
    $('view-panel').innerHTML = `<div class="empty">${icon('alert')}<h3 id="panel-title">No se pudo cargar la biblioteca</h3><p>${esc(e.message)}. Comprueba que Creator MD sigue abierto y recarga la página.</p></div>`;
    fail(e);
  }
})();
