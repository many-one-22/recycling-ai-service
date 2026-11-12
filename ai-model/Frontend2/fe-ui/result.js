// 1. 체크리스트 클릭 토글
window.toggleCheck = function(element) {
  element.classList.toggle('done');
};

// 2. 오류 신고(결과 수정 제보) 모달 제어
let selectedFeedbackLabel = null;
let feedbackSending = false;

// 방금 분석한 결과(category, image_url 등)를 꺼낸다
function getSavedResult() {
  try {
    return JSON.parse(sessionStorage.getItem('predictResult')) || {};
  } catch (error) {
    return {};
  }
}

function setFeedbackMessage(text, isOk) {
  const msg = document.getElementById('feedbackMsg');
  if (!msg) return;
  msg.textContent = text || '';
  msg.hidden = !text;
  msg.classList.toggle('ok', !!isOk);
}

window.openFeedbackModal = function() {
  const modal = document.getElementById('feedbackModal');
  if (!modal) return;

  // 이전에 입력한 내용 초기화
  selectedFeedbackLabel = null;
  feedbackSending = false;
  document.querySelectorAll('#feedbackOptions .opt-btn').forEach((b) => b.classList.remove('selected'));
  const textEl = document.getElementById('feedbackText');
  if (textEl) textEl.value = '';
  const submitBtn = document.getElementById('feedbackSubmit');
  if (submitBtn) submitBtn.disabled = false;
  setFeedbackMessage('');

  // AI가 분류한 결과 보여주기
  const aiEl = document.getElementById('feedbackAiLabel');
  if (aiEl) aiEl.textContent = getSavedResult().category || '알 수 없음';

  modal.style.display = 'flex';
};

window.closeFeedbackModal = function() {
  const modal = document.getElementById('feedbackModal');
  if (modal) {
    modal.style.display = 'none';
  }
};

// 올바른 품목 버튼: 하나만 선택된다
window.selectFeedbackLabel = function(button) {
  document.querySelectorAll('#feedbackOptions .opt-btn').forEach((b) => b.classList.remove('selected'));
  button.classList.add('selected');
  selectedFeedbackLabel = button.dataset.label;
  setFeedbackMessage('');
};

// 제보를 서버로 보낸다. REPORT_MULTIPART 값(api-config.js)에 따라 방식이 달라진다.
async function sendReport(content, aiLabel, imageUrl, token) {
  const headers = { 'Authorization': 'Bearer ' + token };

  if (REPORT_MULTIPART) {
    // 새 API: 사진 파일 + 내용 + AI 분류 결과를 함께 전송
    // (필드 이름은 백엔드 담당과 확인 필요)
    const form = new FormData();
    if (imageUrl) {
      const imgRes = await fetch(API_BASE + imageUrl);
      form.append('image', await imgRes.blob(), 'report.jpg');
    }
    form.append('content', content);
    form.append('ai_label', aiLabel);
    return fetch(API.reports, { method: 'POST', headers, body: form });
  }

  // 현재 API: 내용(JSON)만 받는다. 사진 경로는 내용 끝에 붙여 보낸다.
  headers['Content-Type'] = 'application/json';
  const fullContent = imageUrl ? `${content}\n사진: ${imageUrl}` : content;
  return fetch(API.reports, {
    method: 'POST',
    headers,
    body: JSON.stringify({ content: fullContent })
  });
}

window.submitFeedback = async function() {
  if (feedbackSending) return;

  if (!selectedFeedbackLabel) {
    setFeedbackMessage('올바른 품목을 선택해주세요.');
    return;
  }

  const token = getToken();
  if (!token) {
    setFeedbackMessage('로그인 후 제보할 수 있어요. 마이페이지에서 로그인해주세요.');
    return;
  }

  const result = getSavedResult();
  const aiLabel = result.category || '알 수 없음';
  const extra = (document.getElementById('feedbackText').value || '').trim();

  let content = `[결과 수정 제보] AI 분류: ${aiLabel} → 사용자 선택: ${selectedFeedbackLabel}`;
  if (extra) content += `\n의견: ${extra}`;

  const submitBtn = document.getElementById('feedbackSubmit');
  feedbackSending = true;
  if (submitBtn) submitBtn.disabled = true;
  setFeedbackMessage('전송 중이에요...', true);

  try {
    const res = await sendReport(content, aiLabel, result.image_url, token);

    if (res.ok) {
      setFeedbackMessage('제보가 접수됐어요. 감사합니다!', true);
      setTimeout(window.closeFeedbackModal, 1200);
      return; // 버튼은 그대로 비활성: 같은 제보가 두 번 가지 않게
    }

    if (res.status === 401) {
      setFeedbackMessage('로그인이 만료됐어요. 다시 로그인해주세요.');
    } else {
      setFeedbackMessage('제보 전송에 실패했어요. 잠시 후 다시 시도해주세요.');
    }
  } catch (error) {
    console.warn('[result] 제보 전송 오류:', error);
    setFeedbackMessage('서버에 연결하지 못했어요. 다시 시도해주세요.');
  }

  feedbackSending = false;
  if (submitBtn) submitBtn.disabled = false;
};

// 3. 페이지 로드 시 초기화 및 데이터 렌더링
// 3. 페이지 로드 시 초기화 및 데이터 렌더링
window.addEventListener('DOMContentLoaded', () => {
  const savedData = sessionStorage.getItem('predictResult');

  if (savedData) {
    try {
      const parsedData = JSON.parse(savedData);
      renderResultData(parsedData);
      awardLocalPointsOnce(parsedData);   // 새 분류 결과일 때만 포인트 +10
      recordRecycleOnce(parsedData);      // 서버에 분류 개수 1개 저장 (로그인한 경우)
    } catch (error) {
      console.error('데이터 파싱 실패:', error);
    }
  } else {
    console.warn('[result] sessionStorage에 predictResult가 없습니다. 촬영/업로드부터 다시 진행해주세요.');
  }
});

// ------------------------------------------------------------------
// 분류 1건당 한 번만 처리하기 위한 도우미
//   predictResult(sessionStorage) 안에 "이미 했다"는 표시를 남긴다.
//   새 사진을 찍으면 predictResult가 새로 만들어져서 표시도 초기화된다.
// ------------------------------------------------------------------
function markResult(data, key) {
  data[key] = true;
  try {
    sessionStorage.setItem('predictResult', JSON.stringify(data));
  } catch (error) {
    console.warn('sessionStorage 저장 실패:', error);
  }
}

// 로그인 토큰 (index.js, admin.js와 같은 키)
function getToken() {
  try {
    return localStorage.getItem('access_token');
  } catch (error) {
    return null;
  }
}

// 브라우저에만 쌓이는 포인트. 새로고침해도 한 번만 올라간다.
function awardLocalPointsOnce(data) {
  if (data.pointGiven) return;
  try {
    let currentPoint = parseInt(localStorage.getItem('ecoPoint') || '0', 10);
    currentPoint += 10;
    localStorage.setItem('ecoPoint', currentPoint);

    const pointEl = document.getElementById('myTotalPoint');
    if (pointEl) {
      pointEl.innerText = currentPoint;
    }
    markResult(data, 'pointGiven');
  } catch (error) {
    console.warn('localStorage 접근 실패:', error);
  }
}

// 분류 결과를 서버(recycle_logs)에 1개로 저장. 로그인 안 했으면 건너뛴다.
async function recordRecycleOnce(data) {
  if (data.recycleSaved || !data.category) return;

  const token = getToken();
  if (!token) return;

  try {
    const res = await fetch(API.recycle, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token
      },
      body: JSON.stringify({ item_type: data.category, count: 1 })
    });

    if (res.ok) {
      markResult(data, 'recycleSaved');
    } else {
      // 결과 화면은 그대로 보여야 하므로 화면에는 알리지 않는다
      console.warn('[result] 분류 개수 저장 실패:', res.status);
    }
  } catch (error) {
    console.warn('[result] 분류 개수 저장 중 오류:', error);
  }
}


/**
 * [수정] postEx.py(FastAPI)의 응답 형식에 맞춰 렌더링
 * 응답 예시:
 * {
 *   category: "페트병",
 *   title: "페트병으로 분류돼요",
 *   sub_title: "올바른 분리배출을 실천해주세요",
 *   confidence: 0.954,
 *   guide: "라벨을 떼고, 압착 후 배출하세요",
 *   steps: ["라벨을 떼고", "압착 후 배출하세요"],
 *   image_url: "/static/uploads/xxx.jpg"
 * }
 */
function renderResultData(data) {
  if (!data || !data.category) return;

  const category = data.category || '기타';
  const title = data.title || `${category}입니다`;
  const subTitle = data.sub_title || '';
  const confidence = typeof data.confidence === 'number' ? data.confidence : null;

  const badgeEl = document.getElementById('resCategory');
  const titleEl = document.getElementById('resTitle');

  if (badgeEl) badgeEl.innerText = category;
  if (titleEl) titleEl.innerText = title;

  // 헤드라인 설명(sub_title)
  const descEl = document.querySelector('.headline-desc');
  if (descEl && subTitle) descEl.innerText = subTitle;

  // 신뢰도(confidence) 뱃지 업데이트
  if (confidence !== null) {
    const confidenceEl = document.querySelector('.ai-confidence strong');
    if (confidenceEl) {
      confidenceEl.innerText = `${(confidence * 100).toFixed(1)}%`;
    }
  }

  // 업로드된 이미지 표시 (image_url은 "/static/uploads/..." 형태의 절대경로)
  if (data.image_url) {
    const imgBox = document.getElementById('imgBox');
    if (imgBox) {
      imgBox.innerHTML = `<img src="${API_BASE}${data.image_url}" alt="촬영 이미지">`;
    }
  }

  // 안내 가이드 리스트: steps(배열)가 있으면 그대로 사용, 없으면 guide(문자열)를 줄바꿈 기준으로 분리
  const items = Array.isArray(data.steps) && data.steps.length > 0
    ? data.steps
    : (data.guide ? data.guide.split('\n').filter(text => text.trim() !== '') : []);

  if (items.length > 0) {
    const guideListEl = document.getElementById('guideList');
    if (guideListEl) {
      guideListEl.innerHTML = items.map(item => `
        <li class="check-item" onclick="toggleCheck(this)">
          <span class="check-circle"></span>
          <span class="guide-desc">${item}</span>
        </li>
      `).join('');
    }
  }
}