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
  // 로컬 에코 포인트 누적 처리
  handleLocalPoints();

  // 백엔드 연동 데이터 확인 (sessionStorage 기준)
  const savedData = sessionStorage.getItem('predictResult');

  if (savedData) {
    try {
      const parsedData = JSON.parse(savedData);
      renderResultData(parsedData);
    } catch (error) {
      console.error('데이터 파싱 실패:', error);
    }
  }
});

/**
 * 브라우저 localStorage를 활용한 포인트 누적 함수
 */
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
 * 전달받은 예측 데이터를 화면에 바인딩하는 함수
 */
function renderResultData(data) {
  if (!data || !data.prediction) return;

  const pred = data.prediction;
  const category = pred.category || '기타';
  const guideText = pred.disposal_method || '';

  const badgeEl = document.getElementById('resCategory');
  const titleEl = document.getElementById('resTitle');

  if (badgeEl) badgeEl.innerText = category;
  if (titleEl) titleEl.innerText = `${category}입니다`;

  // 업로드된 이미지 파일 표시
  if (data.saved_filename && data.saved_filename !== '없음') {
    const imgBox = document.getElementById('imgBox');
    if (imgBox) {
      imgBox.innerHTML = `<img src="http://127.0.0.1:5000/static/uploads/${data.saved_filename}" alt="촬영 이미지">`;
    }
  }

  // 안내 가이드 리스트 동적 생성
  if (guideText) {
    const guideListEl = document.getElementById('guideList');
    const items = guideText.split('\n').filter(text => text.trim() !== '');

    if (guideListEl && items.length > 0) {
      guideListEl.innerHTML = items.map(item => `
        <li class="check-item" onclick="toggleCheck(this)">
          <span class="check-circle"></span>
          <span class="guide-desc">${item}</span>
        </li>
      `).join('');
    }
  }
}