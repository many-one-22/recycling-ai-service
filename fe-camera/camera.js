const video = document.getElementById('cameraVideo');
const canvas = document.getElementById('captureCanvas');
const btnShutter = document.getElementById('btnShutter');
const btnSwitch = document.getElementById('btnSwitch');
const btnGallery = document.getElementById('btnGallery');
const galleryInput = document.getElementById('galleryInput');
const btnBack = document.getElementById('btnBack');

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
  } catch (error) {
    console.error('카메라 권한 오류 또는 장치 없음:', error);
    alert('카메라 접근 권한을 허용해주세요.');
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

  // 캡처 데이터 생성 (Base64 JPEG)
  const capturedImage = canvas.toDataURL('image/jpeg', 0.9);
  console.log('촬영 완료: Base64 데이터 준비됨', capturedImage.slice(0, 50) + '...');
  alert('촬영이 완료되었습니다!');
});

// 3. 카메라 전/후면 전환
btnSwitch.addEventListener('click', () => {
  useFacingMode = (useFacingMode === 'environment') ? 'user' : 'environment';
  startCamera();
});

// 4. 갤러리 파일 열기
btnGallery.addEventListener('click', () => {
  galleryInput.click();
});

galleryInput.addEventListener('change', (event) => {
  const file = event.target.files[0];
  if (file) {
    alert(`선택된 이미지: ${file.name}`);
  }
});

// 5. 뒤로가기
btnBack.addEventListener('click', () => {
  if (window.history.length > 1) {
    window.history.back();
  } else {
    window.location.href = 'index.html';
  }
});

// 초기 구동
window.addEventListener('DOMContentLoaded', startCamera);