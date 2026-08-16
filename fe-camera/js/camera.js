/**
 * camera.js
 * 02_카메라 촬영 화면과 03_분석 중 로딩 화면(같은 페이지 내 오버레이)의 동작을 담당합니다.
 * - getUserMedia로 후면 카메라 스트림을 받아 video에 연결
 * - 셔터 버튼 클릭 시 프레임을 캡처하고 로딩 화면으로 전환
 * - api.js를 통해 서버로 이미지 전송 후, 결과를 저장하고 결과 화면으로 이동
 */

const videoEl = document.getElementById("camera-stream");
const shutterBtn = document.getElementById("shutter-btn");
const backBtn = document.getElementById("back-btn");
const cameraView = document.getElementById("camera-view");
const loadingView = document.getElementById("loading-view");
const errorEl = document.getElementById("camera-error");
const captureCanvas = document.getElementById("capture-canvas");

let mediaStream = null;

/**
 * 후면 카메라(facingMode: environment) 스트림을 요청해서 video 엘리먼트에 연결
 */
async function initCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showError("이 브라우저는 카메라 기능(getUserMedia)을 지원하지 않습니다.");
    return;
  }

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
    videoEl.srcObject = mediaStream;
  } catch (error) {
    console.error("카메라 연결 실패:", error);
    if (error.name === "NotAllowedError") {
      showError("카메라 권한이 거부되었습니다. 브라우저 설정에서 카메라 권한을 허용해주세요.");
    } else if (error.name === "NotFoundError") {
      showError("사용 가능한 카메라를 찾을 수 없습니다.");
    } else {
      showError("카메라를 실행하는 중 오류가 발생했습니다.");
    }
  }
}

/**
 * 카메라/네트워크 에러 안내 문구를 화면에 표시
 */
function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function clearError() {
  errorEl.hidden = true;
  errorEl.textContent = "";
}

/**
 * 현재 video 프레임을 canvas에 그려 이미지 Blob으로 캡처
 * @returns {Promise<Blob>}
 */
function captureFrame() {
  const width = videoEl.videoWidth;
  const height = videoEl.videoHeight;
  captureCanvas.width = width;
  captureCanvas.height = height;

  const ctx = captureCanvas.getContext("2d");
  ctx.drawImage(videoEl, 0, 0, width, height);

  return new Promise((resolve) => {
    captureCanvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.9);
  });
}

function showLoadingView() {
  cameraView.hidden = true;
  loadingView.hidden = false;
}

function showCameraView() {
  loadingView.hidden = true;
  cameraView.hidden = false;
}

/**
 * 사용 중인 카메라 스트림 트랙을 정지 (다른 화면으로 이동하기 전 호출)
 */
function stopCamera() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
}

/**
 * 셔터 버튼 클릭 핸들러
 * 캡처 -> 로딩 화면 전환 -> 서버 전송 -> 결과 저장 -> 결과 화면 이동
 */
async function handleCapture() {
  if (!mediaStream) {
    showError("카메라가 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요.");
    return;
  }

  clearError();
  const imageBlob = await captureFrame();
  showLoadingView();

  try {
    // TODO: 백엔드 API 명세 확정 전까지는 api.js의 mock 응답(USE_MOCK_API)으로 동작 확인
    const result = await window.WasteAPI.uploadWasteImage(imageBlob);

    // TODO: sessionStorage 키/저장 방식은 fe-ui 팀원과 협의 후 확정 필요
    sessionStorage.setItem("wasteAnalysisResult", JSON.stringify(result));

    stopCamera();
    window.location.href = "../fe-ui/result.html";
  } catch (error) {
    console.error("이미지 분석 요청 실패:", error);
    showCameraView();
    showError(error.message || "분석 중 오류가 발생했습니다. 다시 시도해주세요.");
  }
}

/**
 * 뒤로가기 버튼 핸들러: 메인 홈 화면으로 이동
 */
function handleBack() {
  stopCamera();
  window.location.href = "../fe-ui/index.html";
}

shutterBtn.addEventListener("click", handleCapture);
backBtn.addEventListener("click", handleBack);
window.addEventListener("DOMContentLoaded", initCamera);
window.addEventListener("beforeunload", stopCamera);
