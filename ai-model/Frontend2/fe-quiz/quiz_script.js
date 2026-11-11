/**
 * quiz_script.js - 오늘의 환경 O/X 퀴즈
 *
 * 흐름
 *   1) GET /api/quiz/today  로 오늘의 문제를 받아온다 (정답은 안 옴)
 *   2) O 또는 X를 누르면 POST /api/quiz/answer 로 제출
 *   3) 서버가 채점해서 정답/해설을 돌려주면 화면에 표시
 *
 * 로그인은 선택이다. 로그인하면 서버에 기록이 남고,
 * 로그인 안 하면 그 브라우저에만(localStorage) 오늘 푼 걸 기억한다.
 */

// 서버 주소는 상대경로로 둔다 (localhost / 배포 / ngrok 어디서든 그대로 동작)
const TODAY_URL = '/api/quiz/today';
const ANSWER_URL = '/api/quiz/answer';
const STATS_URL = '/api/quiz/stats';
const HOME_PAGE = '/fe-ui/index.html';
const SIGN_IN_PAGE = '/fe-ui/sign_in.html';

// 비로그인 사용자의 오늘 풀이 기록 보관용 키
const LOCAL_KEY = 'quiz_last_answer';

const $ = (id) => document.getElementById(id);

let todayData = null;
let submitting = false;

/** 로그인 토큰이 있으면 Authorization 헤더를 만든다 */
function authHeaders() {
  const token = localStorage.getItem('access_token');
  return token ? { 'Authorization': 'Bearer ' + token } : {};
}

/** 브라우저에 저장된 오늘 풀이 기록 읽기 (비로그인용) */
function readLocalAnswer(date) {
  try {
    const raw = localStorage.getItem(LOCAL_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    return saved && saved.date === date ? saved : null;
  } catch (e) {
    return null;
  }
}

function writeLocalAnswer(payload) {
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(payload));
  } catch (e) {
    // 사생활 보호 모드 등에서 저장이 막혀도 퀴즈 자체는 동작해야 한다
    console.warn('로컬 저장 실패:', e);
  }
}

function goHome() {
  window.location.href = HOME_PAGE;
}

/** 화면 상태 전환 */
function showError(message) {
  $('stateLoading').hidden = true;
  $('quizCard').hidden = true;
  $('errorText').textContent = message;
  $('stateError').hidden = false;
}

/** 오늘의 문제 불러오기 */
async function loadToday() {
  let res;
  try {
    res = await fetch(TODAY_URL, { headers: authHeaders() });
  } catch (e) {
    console.error(e);
    showError('서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.');
    return;
  }

  if (!res.ok) {
    let detail = '문제를 불러오지 못했어요.';
    try {
      const err = await res.json();
      if (err && err.detail) detail = err.detail;
    } catch (e) { /* 본문이 JSON이 아니면 기본 문구 사용 */ }
    showError(detail);
    return;
  }

  todayData = await res.json();
  renderQuestion(todayData);

  // 로그인 상태에 따라 하단 영역 처리
  if (todayData.logged_in) {
    loadStats();
  } else {
    $('loginHint').hidden = false;
  }
}

/** 문제 카드 그리기 */
function renderQuestion(data) {
  $('stateLoading').hidden = true;
  $('quizCard').hidden = false;

  const [y, m, d] = data.date.split('-');
  $('dateText').textContent = `${Number(m)}월 ${Number(d)}일의 문제`;
  $('fieldBadge').textContent = data.field;
  $('questionText').textContent = data.question;

  // 이미 푼 경우: 서버 기록(로그인) 또는 브라우저 기록(비로그인)
  const local = data.logged_in ? null : readLocalAnswer(data.date);

  if (data.answered) {
    showResult({
      my_choice: data.my_choice,
      answer: data.answer,
      is_correct: data.is_correct,
      explanation: data.explanation
    }, '오늘 문제는 이미 풀었어요. 내일 새 문제가 나와요!');
  } else if (local) {
    showResult(local, '오늘 문제는 이미 풀었어요. 내일 새 문제가 나와요!');
  }
}

/** O/X 제출 */
async function submitChoice(choice) {
  if (submitting) return;
  submitting = true;
  setButtonsDisabled(true);

  let res;
  try {
    res = await fetch(ANSWER_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ choice })
    });
  } catch (e) {
    console.error(e);
    submitting = false;
    setButtonsDisabled(false);
    alert('서버에 연결하지 못했어요. 다시 시도해 주세요.');
    return;
  }

  if (!res.ok) {
    submitting = false;
    setButtonsDisabled(false);
    alert('채점에 실패했어요. 다시 시도해 주세요.');
    return;
  }

  const result = await res.json();

  // 비로그인 사용자는 브라우저에 기록해 둔다
  if (!result.logged_in) {
    writeLocalAnswer({
      date: result.date,
      my_choice: result.my_choice,
      answer: result.answer,
      is_correct: result.is_correct,
      explanation: result.explanation
    });
  }

  const notice = result.logged_in
    ? (result.already_answered ? '오늘 문제는 이미 풀었어요. 내일 새 문제가 나와요!' : '기록이 저장됐어요. 내일 또 만나요!')
    : '로그인하면 기록이 저장돼요.';

  showResult(result, notice);

  if (result.logged_in) loadStats();
  submitting = false;
}

/** 채점 결과 표시 */
function showResult(result, noticeMessage) {
  const correct = !!result.is_correct;

  // 고른 쪽만 강조하고 나머지는 흐리게
  document.querySelectorAll('.ox-btn').forEach((btn) => {
    btn.disabled = true;
    if (btn.dataset.choice === result.my_choice) {
      btn.classList.add('chosen');
    } else {
      btn.classList.add('dimmed');
    }
  });

  const box = $('resultBox');
  box.classList.toggle('wrong', !correct);
  $('resultVerdict').textContent = correct ? '정답이에요! 🎉' : '아쉬워요 😢';
  $('resultAnswer').textContent = `정답: ${result.answer}`;
  $('resultExplanation').textContent = result.explanation;
  box.hidden = false;

  if (noticeMessage) {
    $('noticeText').textContent = noticeMessage;
    $('noticeText').hidden = false;
  }
  $('cardActions').hidden = false;
}

function setButtonsDisabled(disabled) {
  document.querySelectorAll('.ox-btn').forEach((b) => { b.disabled = disabled; });
}

/** 내 누적 성적 (로그인 시에만) */
async function loadStats() {
  try {
    const res = await fetch(STATS_URL, { headers: authHeaders() });
    if (!res.ok) return;
    const s = await res.json();
    $('statSolved').textContent = s.solved;
    $('statCorrect').textContent = s.correct;
    $('statAccuracy').textContent = s.accuracy + '%';
    $('statStreak').textContent = s.streak;
    $('statsCard').hidden = false;
  } catch (e) {
    console.warn('퀴즈 기록 불러오기 실패:', e);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.ox-btn').forEach((btn) => {
    btn.addEventListener('click', () => submitChoice(btn.dataset.choice));
  });
  loadToday();
});
