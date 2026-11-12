const ITEMS = ['페트병', '캔', '유리병', '종이'];   // 최종 품목 선택지
let allReports = [];
let reportFilter = '';
let allUsers = [];
const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json' };
  let token = null;
  try { token = localStorage.getItem('access_token'); } catch (e) {}
  if (token) headers.Authorization = 'Bearer ' + token;

  const res = await fetch(path, { credentials: 'include', ...options, headers });
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).detail; } catch (e) {}
    const err = new Error(detail || ('요청에 실패했어요 (' + res.status + ')'));
    err.status = res.status;
    throw err;
  }

  if (res.status === 204) return null;
  return res.json().catch(() => null);
}

// DB 시각은 UTC라서 한국 시간으로 바꿔서 보여줘요
function fmtTime(s) {
  if (!s) return '';
  const d = new Date(s.replace(' ', 'T') + 'Z');
  return isNaN(d) ? s : d.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
}

function cell(text, cls) {
  const td = document.createElement('td');
  td.textContent = text;           // textContent라서 제보 내용에 HTML이 있어도 실행되지 않아요
  if (cls) td.className = cls;
  return td;
}

function emptyRow(body, cols, text) {
  const tr = document.createElement('tr');
  const td = cell(text, 'empty');
  td.colSpan = cols;
  tr.appendChild(td);
  body.appendChild(tr);
}

function showMsg(text) {
  const box = $('msg');
  box.textContent = text;
  box.style.display = text ? 'block' : 'none';
}

let toastTimer;
function toast(text) {
  const t = $('toast');
  t.textContent = text;
  t.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.display = 'none'; }, 2500);
}

// 정지/해제/삭제 공통 처리
async function userAction(url, method, body, okMsg, buttons) {
  buttons.forEach((b) => { b.disabled = true; });
  try {
    await api(url, { method, body: body ? JSON.stringify(body) : undefined });
    toast(okMsg);
    await loadAll();
  } catch (e) {
    buttons.forEach((b) => { b.disabled = false; });
    if (e.status === 404 || e.status === 405) {
      toast('서버가 아직 이 기능을 지원하지 않아요. (백엔드 머지 후 가능)');
    } else {
      toast('실패했어요: ' + e.message);
    }
  }
}

function buildUserCard(u) {
  const card = el('div', 'user-card' + (u.is_banned ? ' banned' : ''));

  const head = el('div', 'user-head');
  head.appendChild(el('span', 'uid', '#' + u.id));
  head.appendChild(el('span', 'uemail', u.email || ''));
  if (u.is_admin) head.appendChild(el('span', 'badge', '관리자'));
  if (u.is_banned) head.appendChild(el('span', 'st-badge st-reject', '정지됨'));
  card.appendChild(head);

  const meta = el('div', 'user-meta');
  const cnt = el('span', '', '재활용 ');
  cnt.appendChild(el('strong', '', String(u.recycled_count || 0) + '개'));
  meta.appendChild(cnt);
  meta.appendChild(el('span', '', '가입 ' + fmtTime(u.created_at)));
  card.appendChild(meta);

  if (u.is_banned && u.banned_reason) {
    card.appendChild(el('div', 'ban-reason', '정지 사유: ' + u.banned_reason));
  }

  // 관리자 계정에는 정지/삭제 버튼을 아예 보여주지 않아요
  if (u.is_admin) return card;

  const actions = el('div', 'user-actions');
  const del = el('button', 'btn btn-no', '삭제');
  del.type = 'button';

  if (u.is_banned) {
    const unban = el('button', 'btn', '정지 해제');
    unban.type = 'button';
    unban.addEventListener('click', () => {
      if (confirm(u.email + ' 계정의 정지를 해제할까요?')) {
        userAction(API.userUnban(u.id), 'POST', null, '정지를 해제했어요.', [unban, del]);
      }
    });
    actions.appendChild(unban);
  } else {
    const ban = el('button', 'btn', '정지');
    ban.type = 'button';
    actions.appendChild(ban);

    const form = el('div', 'ban-form');
    const input = document.createElement('input');
    input.type = 'text';
    input.maxLength = 200;
    input.placeholder = '정지 사유 (필수)';
    const go = el('button', 'btn btn-ok', '확인');
    go.type = 'button';
    form.appendChild(input);
    form.appendChild(go);

    ban.addEventListener('click', () => {
      form.classList.toggle('open');
      if (form.classList.contains('open')) input.focus();
    });
    go.addEventListener('click', () => {
      const reason = input.value.trim();
      if (!reason) { toast('정지 사유를 입력해 주세요.'); return; }
      userAction(API.userBan(u.id), 'POST', { reason }, '계정을 정지했어요.', [ban, go, del]);
    });
    actions.appendChild(form);
  }

  del.addEventListener('click', () => {
    if (!confirm(u.email + ' 계정을 삭제할까요?\n삭제하면 되돌릴 수 없어요.')) return;
    if (!confirm('정말 삭제할까요? 이 사용자의 기록도 함께 사라질 수 있어요.')) return;
    userAction(API.userItem(u.id), 'DELETE', null, '계정을 삭제했어요.', [del]);
  });
  actions.appendChild(del);

  card.appendChild(actions);
  return card;
}

function renderUsers(users) {
  allUsers = users;
  const list = $('usersList');
  list.innerHTML = '';
  if (!users.length) {
    list.appendChild(el('div', 'empty', '사용자가 없어요.'));
  } else {
    users.forEach((u) => list.appendChild(buildUserCard(u)));
  }
  $('statUsers').textContent = users.length;
  $('statCount').textContent = users.reduce((sum, u) => sum + (u.recycled_count || 0), 0);
}

// 제보 content 에서 사진 경로 / AI 결과 / 사용자 선택을 꺼내요.
// (새 API가 image_path, ai_label 을 주면 그 값을 우선 써요)
function parseReport(r) {
  const content = r.content || '';
  const photoM = content.match(/사진:\s*(\S+)/);
  const aiM = content.match(/AI 분류:\s*(.+?)\s*→/);
  const userM = content.match(/사용자 선택:\s*(\S+)/);
  return {
    photo: r.image_path || (photoM ? photoM[1] : ''),
    aiLabel: r.ai_label || (aiM ? aiM[1] : ''),
    userLabel: userM ? userM[1] : '',
    text: content.replace(/\n?사진:\s*\S+/, '').trim(),
  };
}

function safeSrc(p) {
  if (!p) return '';
  if (/^https?:\/\//.test(p)) return p;
  return p.startsWith('/') ? p : '/' + p;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;   // textContent: 제보 내용의 HTML 은 실행되지 않아요
  return e;
}

function statusBadge(status) {
  const cls = status === '처리완료' ? 'st-done' : status === '반려' ? 'st-reject' : 'st-wait';
  return el('span', 'st-badge ' + cls, status || '대기중');
}

async function handleResolve(r, status, label, buttons) {
  buttons.forEach((b) => { b.disabled = true; });
  try {
    await api(API.reportItem(r.id), {
      method: 'PATCH',
      body: JSON.stringify({ status, admin_label: label }),
    });
    toast(status === '처리완료' ? '처리완료로 바꿨어요.' : '반려했어요.');
    await loadAll();
  } catch (e) {
    buttons.forEach((b) => { b.disabled = false; });
    if (e.status === 422 && status === '반려') {
      toast('서버가 아직 반려를 지원하지 않아요. (백엔드 머지 후 가능)');
    } else {
      toast('처리에 실패했어요: ' + e.message);
    }
  }
}

function buildReportCard(r) {
  const p = parseReport(r);
  const status = r.status || '대기중';
  const card = el('div', 'report-card');

  const head = el('div', 'report-head');
  head.appendChild(el('span', 'rid', '#' + r.id));
  head.appendChild(statusBadge(status));
  head.appendChild(el('span', 'rtime', fmtTime(r.created_at)));
  card.appendChild(head);

  card.appendChild(el('div', 'report-email', r.email || ''));

  const body = el('div', 'report-body');
  if (p.photo) {
    const img = el('img', 'report-photo');
    img.src = safeSrc(p.photo);
    img.alt = '제보 사진';
    img.addEventListener('error', () => {
      const ph = el('div', 'report-photo none', '사진 없음');
      img.replaceWith(ph);
    });
    body.appendChild(img);
  } else {
    body.appendChild(el('div', 'report-photo none', '사진 없음'));
  }

  const info = el('div', 'report-info');
  if (p.aiLabel) {
    const row = el('div', 'row');
    row.appendChild(el('span', 'k', 'AI 결과'));
    row.appendChild(el('strong', '', p.aiLabel));
    info.appendChild(row);
  }
  if (p.userLabel) {
    const row = el('div', 'row');
    row.appendChild(el('span', 'k', '사용자 선택'));
    row.appendChild(el('strong', '', p.userLabel));
    info.appendChild(row);
  }
  if (r.admin_label) {
    const row = el('div', 'row');
    row.appendChild(el('span', 'k', '최종 품목'));
    row.appendChild(el('strong', '', r.admin_label));
    info.appendChild(row);
  }
  info.appendChild(el('div', 'report-text', p.text));
  body.appendChild(info);
  card.appendChild(body);

  if (status === '대기중') {
    const actions = el('div', 'report-actions');
    actions.appendChild(el('span', 'lbl', '최종 품목'));
    const sel = document.createElement('select');
    ITEMS.forEach((it) => {
      const o = document.createElement('option');
      o.value = it; o.textContent = it;
      sel.appendChild(o);
    });
    if (ITEMS.includes(p.userLabel)) sel.value = p.userLabel;
    actions.appendChild(sel);

    const ok = el('button', 'btn btn-ok', '처리완료');
    ok.type = 'button';
    const no = el('button', 'btn btn-no', '반려');
    no.type = 'button';
    const btns = [ok, no, sel];
    ok.addEventListener('click', () => handleResolve(r, '처리완료', sel.value, btns));
    no.addEventListener('click', () => {
      if (confirm('이 제보를 반려할까요?')) handleResolve(r, '반려', null, btns);
    });
    actions.appendChild(ok);
    actions.appendChild(no);
    card.appendChild(actions);
  }
  return card;
}

function drawReports() {
  const list = $('reportsList');
  list.innerHTML = '';
  const shown = reportFilter ? allReports.filter((r) => (r.status || '대기중') === reportFilter) : allReports;
  if (!shown.length) {
    list.appendChild(el('div', 'empty', '해당하는 제보가 없어요.'));
    return;
  }
  shown.forEach((r) => list.appendChild(buildReportCard(r)));
}

function renderReports(reports) {
  allReports = reports;
  $('statWait').textContent = reports.filter((r) => (r.status || '대기중') === '대기중').length;
  drawReports();
}

function showError(e) {
  if ([401, 403, 503].includes(e.status)) {
    showMsg('관리자만 볼 수 있어요. (' + e.message + ')');
  } else {
    showMsg('불러오지 못했어요: ' + e.message);
  }
}

async function loadReportsOnly() {
  try { $('statWait').textContent = (await api(API.adminReports)).filter((r) => r.status === '대기중').length; }
  catch (e) {}
}

async function loadAll() {
  showMsg('');
  try {
    const [users, reports] = await Promise.all([api(API.adminUsers), api(API.adminReports)]);
    renderUsers(users);
    renderReports(reports);
    loadStats();
  } catch (e) {
    showError(e);
  }
}

function selectTab(name) {
  const map = { users: 'Users', reports: 'Reports', stats: 'Stats' };
  Object.keys(map).forEach((n) => {
    $('panel' + map[n]).classList.toggle('hidden', n !== name);
    $('tab' + map[n]).classList.toggle('active', n === name);
  });
}

$('tabUsers').addEventListener('click', () => selectTab('users'));
$('tabReports').addEventListener('click', () => selectTab('reports'));
$('tabStats').addEventListener('click', () => selectTab('stats'));
$('reportFilter').addEventListener('click', (ev) => {
  const chip = ev.target.closest('.chip');
  if (!chip) return;
  reportFilter = chip.dataset.status;
  document.querySelectorAll('#reportFilter .chip').forEach((c) => c.classList.toggle('active', c === chip));
  drawReports();
});

$('btnRefresh').addEventListener('click', loadAll);

// ================= 통계 =================
function toPairs(data, labelKeys, valueKeys) {
  if (!data) return [];
  if (Array.isArray(data)) {
    return data.map((d) => {
      const lk = labelKeys.find((k) => d[k] !== undefined);
      const vk = valueKeys.find((k) => d[k] !== undefined);
      return [String(lk ? d[lk] : ''), Number(vk ? d[vk] : 0) || 0];
    });
  }
  return Object.entries(data).map(([k, v]) => [k, Number(v) || 0]);
}

function note(box, text) {
  box.innerHTML = '';
  box.appendChild(el('div', 'chart-note', text));
}

function drawBars(box, pairs, emptyText) {
  box.innerHTML = '';
  if (!pairs.length) return note(box, emptyText || '데이터가 없어요.');
  const max = Math.max(1, ...pairs.map((p) => p[1]));
  pairs.forEach(([name, v]) => {
    const row = el('div', 'hbar');
    row.appendChild(el('span', 'name', name));
    const track = el('div', 'track');
    const fill = el('div', 'fill');
    fill.style.width = (v / max * 100) + '%';
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el('span', 'val', String(v)));
    box.appendChild(row);
  });
}

// 서버는 기록이 있는 날만 주기 때문에, 비어 있는 날은 0으로 채워요
function fillDays(pairs, days) {
  const map = {};
  pairs.forEach(([d, v]) => { map[d.slice(0, 10)] = v; });
  const fmt = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' });  // YYYY-MM-DD
  const out = [];
  for (let i = days - 1; i >= 0; i--) {
    const key = fmt.format(new Date(Date.now() - i * 86400000));
    out.push([key, map[key] || 0]);
  }
  return out;
}

function drawLine(box, points) {
  box.innerHTML = '';
  const W = 340, H = 170, L = 30, R = 10, T = 10, B = 26;
  const max = Math.max(1, ...points.map((p) => p[1]));
  const top = max <= 4 ? 4 : Math.ceil(max / 4) * 4;
  const x = (i) => L + (W - L - R) * (points.length === 1 ? 0.5 : i / (points.length - 1));
  const y = (v) => T + (H - T - B) * (1 - v / top);
  const NS = 'http://www.w3.org/2000/svg';
  const mk = (tag, attrs) => {
    const e = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach((k) => e.setAttribute(k, attrs[k]));
    return e;
  };
  const md = (s) => { const p = s.split('-'); return Number(p[1]) + '/' + Number(p[2]); };

  const svg = mk('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', role: 'img', 'aria-label': '최근 재활용 개수 추이' });
  for (let t = 0; t <= 4; t++) {
    const v = top * t / 4;
    svg.appendChild(mk('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), class: 'grid' }));
    const tx = mk('text', { x: L - 6, y: y(v) + 3, 'text-anchor': 'end', class: 'axis' });
    tx.textContent = v;
    svg.appendChild(tx);
  }
  svg.appendChild(mk('polyline', { class: 'line', points: points.map((p, i) => x(i) + ',' + y(p[1])).join(' ') }));

  const readout = el('div', 'readout');
  const show = (p) => { readout.textContent = md(p[0]) + ' · ' + p[1] + '개'; };
  points.forEach((p, i) => {
    const lb = mk('text', { x: x(i), y: H - 8, 'text-anchor': 'middle', class: 'axis' });
    lb.textContent = md(p[0]);
    svg.appendChild(lb);
    svg.appendChild(mk('circle', { cx: x(i), cy: y(p[1]), r: 4, class: 'dot' }));
    const hit = mk('circle', { cx: x(i), cy: y(p[1]), r: 14, class: 'hit' });
    hit.addEventListener('pointerenter', () => show(p));
    hit.addEventListener('click', () => show(p));
    svg.appendChild(hit);
  });
  box.appendChild(svg);
  box.appendChild(readout);
  show(points[points.length - 1]);
}

function drawKpis(s) {
  const box = $('kpis');
  box.innerHTML = '';
  [
    ['전체 사용자', s.total_users],
    ['최근 7일 활성', s.active_users_7d],
    ['누적 재활용', s.total_recycled],
    ['대기중 제보', s.pending_reports],
    ['정지 계정', s.banned_users],
  ].forEach(([label, v]) => {
    const k = el('div', 'kpi');
    k.appendChild(el('div', 'label', label));
    k.appendChild(el('div', 'value', v === undefined || v === null ? '-' : String(v)));
    box.appendChild(k);
  });
}

async function loadStats() {
  const settle = (p) => p.then((v) => ({ ok: true, v }), () => ({ ok: false }));
  const [sum, daily, items, rank, reps] = await Promise.all([
    settle(api(API.statsSummary)),
    settle(api(API.statsDaily(7))),
    settle(api(API.statsItems)),
    settle(api(API.statsRanking(5))),
    settle(api(API.statsReports)),
  ]);
  const wait = '통계 API가 아직 없어요. (백엔드 머지 후 표시돼요)';

  // 요약 카드: 서버 값이 있으면 그걸, 없으면 이미 불러온 목록으로 계산
  if (sum.ok) {
    drawKpis(sum.v);
  } else {
    drawKpis({
      total_users: allUsers.length,
      total_recycled: allUsers.reduce((a, u) => a + (u.recycled_count || 0), 0),
      pending_reports: allReports.filter((r) => (r.status || '대기중') === '대기중').length,
    });
  }

  if (daily.ok) {
    const pts = fillDays(toPairs(daily.v, ['date', 'day'], ['count', 'total', 'recycled_count']), 7);
    drawLine($('chartDaily'), pts);
  } else {
    note($('chartDaily'), wait);
  }

  if (items.ok) {
    const pairs = toPairs(items.v, ['item_type', 'item', 'name'], ['count', 'total']).sort((a, b) => b[1] - a[1]);
    drawBars($('chartItems'), pairs, '아직 재활용 기록이 없어요.');
  } else {
    note($('chartItems'), wait);
  }

  if (rank.ok) {
    const pairs = toPairs(rank.v, ['email', 'name'], ['count', 'total', 'recycled_count']);
    drawBars($('chartRank'), pairs, '아직 재활용 기록이 없어요.');
  } else {
    // 서버 랭킹이 없어도 사용자 목록으로 TOP 5 를 만들 수 있어요
    const top = allUsers.filter((u) => (u.recycled_count || 0) > 0)
      .sort((a, b) => b.recycled_count - a.recycled_count).slice(0, 5)
      .map((u) => [(u.email || '').split('@')[0], u.recycled_count]);
    drawBars($('chartRank'), top, '아직 재활용 기록이 없어요.');
  }

  if (reps.ok) {
    drawBars($('chartReports'), toPairs(reps.v, ['status', 'name'], ['count', 'total']), '접수된 제보가 없어요.');
  } else {
    const c = {};
    allReports.forEach((r) => { const s = r.status || '대기중'; c[s] = (c[s] || 0) + 1; });
    drawBars($('chartReports'), Object.entries(c), '접수된 제보가 없어요.');
  }
}

loadAll();