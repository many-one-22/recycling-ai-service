const STATUSES = ['대기중', '처리완료'];
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
  return res.json();
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

function renderUsers(users) {
  const body = $('usersBody');
  body.innerHTML = '';
  if (!users.length) return emptyRow(body, 4, '사용자가 없어요.');
  users.forEach((u) => {
    const tr = document.createElement('tr');
    tr.appendChild(cell(u.id));
    const emailTd = cell(u.email);
    if (u.is_admin) {
      const b = document.createElement('span');
      b.className = 'badge';
      b.textContent = '관리자';
      emailTd.appendChild(b);
    }
    tr.appendChild(emailTd);
    tr.appendChild(cell(u.recycled_count, 'num'));
    tr.appendChild(cell(fmtTime(u.created_at)));
    body.appendChild(tr);
  });
  $('statUsers').textContent = users.length;
  $('statCount').textContent = users.reduce((sum, u) => sum + (u.recycled_count || 0), 0);
}

function paintSelect(sel) {
  sel.className = sel.value === '처리완료' ? 's-done' : 's-wait';
}

function renderReports(reports) {
  const body = $('reportsBody');
  body.innerHTML = '';
  $('statWait').textContent = reports.filter((r) => r.status === '대기중').length;
  if (!reports.length) return emptyRow(body, 5, '접수된 제보가 없어요.');
  reports.forEach((r) => {
    const tr = document.createElement('tr');
    tr.appendChild(cell(r.id));
    tr.appendChild(cell(r.email));
    tr.appendChild(cell(r.content));

    const statusTd = document.createElement('td');
    const sel = document.createElement('select');
    STATUSES.forEach((s) => {
      const o = document.createElement('option');
      o.value = s; o.textContent = s;
      sel.appendChild(o);
    });
    sel.value = STATUSES.includes(r.status) ? r.status : '대기중';
    paintSelect(sel);
    let prev = sel.value;
    sel.addEventListener('change', async () => {
      try {
        await api('/admin/reports/' + r.id, { method: 'PATCH', body: JSON.stringify({ status: sel.value }) });
        prev = sel.value;
        paintSelect(sel);
        toast('상태를 바꿨어요.');
        loadReportsOnly();
      } catch (e) {
        sel.value = prev;
        paintSelect(sel);
        toast('상태 변경에 실패했어요: ' + e.message);
      }
    });
    statusTd.appendChild(sel);
    tr.appendChild(statusTd);

    tr.appendChild(cell(fmtTime(r.created_at)));
    body.appendChild(tr);
  });
}

function showError(e) {
  if ([401, 403, 503].includes(e.status)) {
    showMsg('관리자만 볼 수 있어요. (' + e.message + ')');
  } else {
    showMsg('불러오지 못했어요: ' + e.message);
  }
}

async function loadReportsOnly() {
  try { $('statWait').textContent = (await api('/admin/reports')).filter((r) => r.status === '대기중').length; }
  catch (e) {}
}

async function loadAll() {
  showMsg('');
  try {
    const [users, reports] = await Promise.all([api('/admin/users'), api('/admin/reports')]);
    renderUsers(users);
    renderReports(reports);
  } catch (e) {
    showError(e);
  }
}

function selectTab(name) {
  const isUsers = name === 'users';
  $('panelUsers').classList.toggle('hidden', !isUsers);
  $('panelReports').classList.toggle('hidden', isUsers);
  $('tabUsers').classList.toggle('active', isUsers);
  $('tabReports').classList.toggle('active', !isUsers);
}

$('tabUsers').addEventListener('click', () => selectTab('users'));
$('tabReports').addEventListener('click', () => selectTab('reports'));
$('btnRefresh').addEventListener('click', loadAll);
loadAll();