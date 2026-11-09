// ------------------------------------------------------------------
// 메인 페이지 동작
//   1) 로그인 상태 표시
//   2) 사진 촬영 -> 카메라 페이지로 이동
//   3) 갤러리 선택 -> 바로 서버에 올려서 분석 -> 결과 페이지로 이동
//   4) 아직 안 만든 메뉴는 "준비 중" 안내
//
// 주소는 상대경로를 쓴다. 같은 서버가 화면과 API를 함께 서빙하므로
// localhost / ngrok / 실제 배포 주소 어디서 열어도 그대로 동작한다.
// ------------------------------------------------------------------
const PREDICT_URL = '/predict';
const ME_URL = '/api/user/me';

const CAMERA_PAGE = '/fe-camera/camera.html';
const RESULT_PAGE = '/fe-ui/result.html';
const SIGN_IN_PAGE = '/fe-ui/sign_in.html';
const MY_PAGE = '/fe-ui/my_page.html';

const btnCamera = document.getElementById('btnCamera');
const btnGallery = document.getElementById('btnGallery');
const galleryInput = document.getElementById('galleryInput');
const userChip = document.getElementById('userChip');
const loginLink = document.getElementById('loginLink');
const loadingOverlay = document.getElementById('loadingOverlay');
const toastEl = document.getElementById('toast');

let toastTimer = null;

function showToast(message) {
  toastEl.textContent = message;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, 2000);
}

// ------------------------------------------------------------------
// 1) 로그인 상태 확인
//    로그인은 필수가 아니다. 로그인 안 해도 촬영/분석은 쓸 수 있고,
//    로그인한 경우에만 이름을 보여준다.
// ------------------------------------------------------------------
async function loadLoginState() {
  const token = localStorage.getItem('access_token');

  if (!token) {
    loginLink.hidden = false;
    return;
  }

  try {
    const res = await fetch(ME_URL, {
      headers: { 'Authorization': 'Bearer ' + token }
    });

    if (res.status === 401) {
      // 토큰이 만료됐거나 탈퇴한 계정 -> 로그아웃 상태로 되돌림
      localStorage.removeItem('access_token');
      loginLink.hidden = false;
      return;
    }

    if (!res.ok) throw new Error('사용자 정보 조회 실패: ' + res.status);

    const user = await res.json();
    userChip.textContent = `${user.name}님`;
    userChip.hidden = false;
  } catch (err) {
    // 서버가 꺼져 있어도 메인 화면 자체는 보여야 하므로 조용히 넘어감
    console.warn('[index] 로그인 상태 확인 실패:', err);
    loginLink.hidden = false;
  }
}

// ------------------------------------------------------------------
// 2) 사진 촬영 -> 카메라 페이지
// ------------------------------------------------------------------
btnCamera.addEventListener('click', () => {
  window.location.href = CAMERA_PAGE;
});

// ------------------------------------------------------------------
// 3) 갤러리에서 선택 -> 바로 업로드 후 분석
// ------------------------------------------------------------------
btnGallery.addEventListener('click', () => {
  galleryInput.click();
});

galleryInput.addEventListener('change', (event) => {
  const file = event.target.files[0];
  if (!file) return;
  uploadImage(file, file.name);
  // 같은 파일을 다시 골라도 change 이벤트가 나도록 초기화
  event.target.value = '';
});

async function uploadImage(file, filename) {
  setBusy(true);

  const formData = new FormData();
  formData.append('image_file', file, filename);

  try {
    const response = await fetch(PREDICT_URL, { method: 'POST', body: formData });

    if (!response.ok) {
      throw new Error('서버 응답 오류: ' + response.status);
    }

    const data = await response.json();

    // 결과 페이지(result.js)가 읽어가는 자리에 저장
    sessionStorage.setItem('predictResult', JSON.stringify(data));
    window.location.href = RESULT_PAGE;
  } catch (err) {
    console.error('[index] 분석 실패:', err);
    setBusy(false);
    showToast('분석에 실패했어요. 잠시 후 다시 시도해주세요.');
  }
}

function setBusy(busy) {
  loadingOverlay.hidden = !busy;
  btnCamera.disabled = busy;
  btnGallery.disabled = busy;
}

// ------------------------------------------------------------------
// 4) 아직 구현되지 않은 메뉴 처리
//    (수거함 위치 / 환경 퀴즈 페이지가 생기면 href만 바꿔주면 됨)
// ------------------------------------------------------------------
document.querySelectorAll('.nav-item[data-soon]').forEach((item) => {
  item.addEventListener('click', (event) => {
    event.preventDefault();
    showToast(`${item.dataset.soon} 기능은 준비 중이에요`);
  });
});

// ------------------------------------------------------------------
loadLoginState();
