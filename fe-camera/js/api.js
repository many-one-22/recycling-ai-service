/**
 * api.js
 * 백엔드 서버와의 통신을 담당하는 독립 모듈.
 * camera.js뿐 아니라 나중에 fe-ui/index.html 쪽에서도 재사용할 수 있도록
 * 특정 화면 로직에 종속되지 않게 작성했습니다.
 * 번들러 없이 <script> 태그로 그대로 로드해서 쓰므로 window.WasteAPI로 노출합니다.
 */

// TODO: 백엔드(Flask + ngrok) 주소가 확정되면 .env 또는 별도 상수 파일로 분리 예정
const API_BASE_URL = "https://YOUR-NGROK-SUBDOMAIN.ngrok-free.app";
// TODO: 실제 이미지 분석 엔드포인트 경로로 교체
const ANALYZE_ENDPOINT = `${API_BASE_URL}/api/analyze`;

const REQUEST_TIMEOUT_MS = 15000;

// 백엔드 API 명세가 확정되기 전까지 화면 흐름을 테스트하기 위한 mock 모드
// TODO: 백엔드 연동 완료되면 false로 변경
const USE_MOCK_API = true;

/**
 * 촬영한 폐기물 이미지를 백엔드로 전송하고 분석 결과를 받아오는 함수
 * @param {Blob} imageBlob - canvas에서 캡처한 이미지 Blob
 * @returns {Promise<Object>} 분석 결과 객체 (예: { category, instructions })
 */
async function uploadWasteImage(imageBlob) {
  if (USE_MOCK_API) {
    return mockUploadWasteImage();
  }

  // TODO: 백엔드 요청 형식 확정 필요 (현재는 multipart/form-data로 가정)
  const formData = new FormData();
  formData.append("image", imageBlob, "capture.jpg");

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(ANALYZE_ENDPOINT, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`서버 응답 오류 (status: ${response.status})`);
    }

    // TODO: 백엔드 응답(JSON) 스키마 확정되면 아래 파싱/필드명 확인 및 수정
    // 예상 응답 형태 (임시):
    // { "category": "유리병", "instructions": ["내용물 비우기", "라벨 제거", "투명 유리병함 배출"] }
    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.");
    }
    throw new Error(`이미지 업로드에 실패했습니다: ${error.message}`);
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * 백엔드 연결 전, 화면 전환(촬영 -> 로딩 -> 결과)을 테스트하기 위한 더미 응답
 */
function mockUploadWasteImage() {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        category: "유리병",
        instructions: [
          "내용물을 비우고 헹궈주세요",
          "라벨과 뚜껑을 제거해주세요",
          "투명 유리병 수거함에 배출해주세요",
        ],
      });
    }, 1500);
  });
}

window.WasteAPI = {
  uploadWasteImage,
};
