// DOM 요소 가져오기
const captureBtn = document.getElementById('capture-btn');
const cameraView = document.getElementById('camera-view');
const loadingView = document.getElementById('loading-view');

// 촬영 버튼 클릭 이벤트 리스너
captureBtn.addEventListener('click', () => {
    // 1. 카메라 화면 숨기기
    cameraView.classList.add('hidden');
    
    // 2. 로딩 화면 보여주기
    loadingView.classList.remove('hidden');
    
    console.log("촬영 버튼 클릭: AI 분석 로딩 시작");

    // [시연용 타이머] 3초 후에 백엔드에서 응답이 온 상황을 가정하고 다시 카메라 화면으로 복귀
    // (2주차에 이 부분에 Fetch API 연동 코드가 들어갑니다)
    setTimeout(() => {
        alert("1주차 기능 확인: 로딩 화면 작동 완료!");
        loadingView.classList.add('hidden');
        cameraView.classList.remove('hidden');
    }, 3000); 
});