// ==========================================
// 1. DOM 요소 선택
// ==========================================
const videoElement = document.getElementById('webcam'); // 카메라 영상 태그
const captureBtn = document.getElementById('capture-btn');
const cameraView = document.getElementById('camera-view');
const loadingView = document.getElementById('loading-view');

// ==========================================
// 2. 카메라 실행 함수 (getUserMedia)
// ==========================================
async function startCamera() {
    // 브라우저의 mediaDevices 지원 여부 확인
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('이 브라우저는 카메라 연동(getUserMedia API)을 지원하지 않습니다.');
        return;
    }

    // 카메라 제약 조건 설정 (노트북 웹캠 기본)
    const constraints = {
        video: {
            width: { ideal: 1280 },
            height: { ideal: 720 },
            facingMode: 'user' // 노트북 기본 전면 카메라
        },
        audio: false // 음성 비활성화
    };

    try {
        // 브라우저 권한 요청 및 라이브 스트림 가져오기
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        
        // video 태그에 스트림 연결
        videoElement.srcObject = stream;
        console.log("카메라 스트림 연동 성공");
    } catch (error) {
        console.error("카메라 연동 실패:", error);

        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
            alert('카메라 접근 권한이 거부되었습니다. 브라우저 주소창 왼쪽 설정에서 권한을 허용해 주세요.');
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
            alert('연결된 카메라 장치를 찾을 수 없습니다.');
        } else {
            alert(`카메라 오류: ${error.message}`);
        }
    }
}

// ==========================================
// 3. 이벤트 리스너 및 실행
// ==========================================

// 페이지가 로드되면 즉시 카메라 켜기
window.addEventListener('DOMContentLoaded', startCamera);

// 촬영 버튼 클릭 이벤트 (기존 화면 전환 로직 유지)
captureBtn.addEventListener('click', () => {
    // 1. 카메라 화면 숨기기
    cameraView.classList.add('hidden');
    
    // 2. 로딩 화면 보여주기
    loadingView.classList.remove('hidden');
    
    console.log("촬영 버튼 클릭: AI 분석 로딩 시작");

    // [시연용 타이머] 3초 후 로딩 종료 및 카메라 화면 복귀
    setTimeout(() => {
        alert("1주차/2주차 기능 확인: 카메라 및 로딩 화면 작동 완료!");
        loadingView.classList.add('hidden');
        cameraView.classList.remove('hidden');
    }, 3000); 
});