// -------------------------------------------------------------
// 설정
// -------------------------------------------------------------
// FastAPI(postEx.py)를 uvicorn --port 8080으로 실행하는 것 기준
const API_BASE = "http://localhost:8080";
const PREDICT_URL = `${API_BASE}/predict`;

const video = document.getElementById('cameraVideo');
const canvas = document.getElementById('captureCanvas');
const btnShutter = document.getElementById('btnShutter');
const btnSwitch = document.getElementById('btnSwitch');
const btnBack = document.getElementById('btnBack');
const loadingOverlay = document.getElementById('loadingOverlay');

let currentStream = null;
let useFacingMode = 'environment'; // 모바일 후면 카메라 우선

// 1. 카메라 시작
async function startCamera() {
  if (currentStream) {
    currentStream.getTracks().forEach(track => track.stop());
  }

  const constraints = {
    audio: false,
    video: {
      facingMode: useFacingMode,
      width: { ideal: 1280 },
      height: { ideal: 720 }
    }
  };

  try {
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    currentStream = stream;
    video.srcObject = stream;
    console.log('[camera] 카메라 스트림 시작됨');
  } catch (error) {
    console.error('[camera] 카메라 권한 오류 또는 장치 없음:', error);
    alert('카메라 접근 권한을 허용해주세요.');
  }
}

function stopCamera() {
  if (currentStream) {
    currentStream.getTracks().forEach(track => track.stop());
    currentStream = null;
  }
}

// 2. 셔터 클릭 시 캡처
btnShutter.addEventListener('click', () => {
  if (!video.videoWidth) {
    alert('카메라 화면이 준비되지 않았습니다.');
    return;
  }

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(
    (blob) => {
      if (!blob) {
        console.error('[camera] canvas.toBlob 결과가 비어있음');
        alert('사진 캡처에 실패했어요. 다시 시도해주세요.');
        return;
      }
      console.log('[camera] 캡처 완료, 업로드 시작', blob);
      uploadImage(blob, 'capture.jpg');
    },
    'image/jpeg',
    0.9
  );
});

// 3. 카메라 전/후면 전환
btnSwitch.addEventListener('click', () => {
  useFacingMode = (useFacingMode === 'environment') ? 'user' : 'environment';
  startCamera();
});

// 4. 뒤로가기
btnBack.addEventListener('click', () => {
  if (window.history.length > 1) {
    window.history.back();
  } else {
    window.location.href = '/fe-ui/index.html';
  }
});

// -------------------------------------------------------------
// 서버 업로드 + 결과 페이지 이동
// -------------------------------------------------------------
async function uploadImage(fileOrBlob, filename) {
  if (loadingOverlay) loadingOverlay.style.display = 'flex';
  btnShutter.disabled = true;

  const formData = new FormData();
  formData.append('image_file', fileOrBlob, filename);

  try {
    console.log('[camera] fetch 요청 시작:', PREDICT_URL);
    const response = await fetch(PREDICT_URL, {
      method: 'POST',
      body: formData,
    });

    console.log('[camera] 응답 상태:', response.status);

    if (!response.ok) {
      throw new Error(`서버 응답 오류: ${response.status}`);
    }

    const data = await response.json();
    console.log('[camera] 예측 결과:', data);

    stopCamera();
    sessionStorage.setItem('predictResult', JSON.stringify(data));
    window.location.href = '/fe-ui/result.html';
  } catch (err) {
    // [중요] 여기서 잡히는 에러 메시지를 브라우저 콘솔(F12)에서 꼭 확인하세요.
    // 흔한 원인: (1) predict.py 서버가 안 켜져 있음
    //           (2) camera.html을 더블클릭(file://)으로 열어서 fetch가 막힘 -> 로컬 서버로 열어야 함
    //           (3) API_BASE 주소가 실제 서버 주소와 다름
    console.error('[camera] 업로드/예측 실패:', err);
    if (loadingOverlay) loadingOverlay.style.display = 'none';
    btnShutter.disabled = false;
    alert('분석 중 문제가 발생했어요. 콘솔(F12)에서 에러 메시지를 확인해주세요.');
  }
}

// 페이지를 벗어날 때 카메라 자원 정리
window.addEventListener('pagehide', stopCamera);

// 초기 구동
window.addEventListener('DOMContentLoaded', startCamera);