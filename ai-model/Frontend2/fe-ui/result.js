// FastAPI(postEx.py)를 uvicorn --port 8080으로 실행하는 것 기준
const API_BASE = "http://localhost:8080";

// 1. 체크리스트 클릭 토글
window.toggleCheck = function(element) {
  element.classList.toggle('done');
};

// 2. 오류 신고 모달 제어
window.openFeedbackModal = function() {
  const modal = document.getElementById('feedbackModal');
  if (modal) {
    modal.style.display = 'flex';
  }
};

window.closeFeedbackModal = function() {
  const modal = document.getElementById('feedbackModal');
  if (modal) {
    modal.style.display = 'none';
  }
};

window.submitFeedback = function(chosenCategory) {
  alert(`제보 감사합니다! "${chosenCategory}"(으)로 피드백이 등록되었습니다.`);
  window.closeFeedbackModal();
};

// 3. 페이지 로드 시 초기화 및 데이터 렌더링
window.addEventListener('DOMContentLoaded', () => {
  handleLocalPoints();

  const savedData = sessionStorage.getItem('predictResult');

  if (savedData) {
    try {
      const parsedData = JSON.parse(savedData);
      renderResultData(parsedData);
    } catch (error) {
      console.error('데이터 파싱 실패:', error);
    }
  } else {
    console.warn('[result] sessionStorage에 predictResult가 없습니다. 촬영/업로드부터 다시 진행해주세요.');
  }
});

function handleLocalPoints() {
  try {
    let currentPoint = parseInt(localStorage.getItem('ecoPoint') || '0', 10);
    currentPoint += 10;
    localStorage.setItem('ecoPoint', currentPoint);

    const pointEl = document.getElementById('myTotalPoint');
    if (pointEl) {
      pointEl.innerText = currentPoint;
    }
  } catch (error) {
    console.warn('localStorage 접근 실패:', error);
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