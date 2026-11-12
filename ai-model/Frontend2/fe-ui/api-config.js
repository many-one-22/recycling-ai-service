// ------------------------------------------------------------------
// api-config.js - 프론트가 부르는 서버 주소를 한곳에 모아둔 파일
//
// 백엔드가 새 API(/api/...)로 바뀌어 머지되면
// 아래 API_PREFIX 한 줄만 '/api' 로 바꾸면 된다.
// ------------------------------------------------------------------
const API_PREFIX = '';   // 지금은 ''  /  머지 후에는 '/api'

// 오류 제보 전송 방식. 새 API(사진 파일 업로드)가 머지되면 true 로 바꾼다.
const REPORT_MULTIPART = false;

// 이미지 주소 앞에 붙는 서버 주소. 상대경로('')라서 localhost, 휴대폰, 배포 어디서든 동작한다.
const API_BASE = '';

const API = {
  // 분리배출 기록 / 오류 제보 (로그인 필요)
  recycle: `${API_PREFIX}/recycle`,
  reports: `${API_PREFIX}/reports`,

  // 관리자
  adminUsers: `${API_PREFIX}/admin/users`,
  adminReports: `${API_PREFIX}/admin/reports`,
  reportItem: (id) => `${API_PREFIX}/admin/reports/${id}`,

  // 아래는 새 API용 (다음 단계에서 사용, 백엔드 머지 후에 동작)
  userBan: (id) => `${API_PREFIX}/admin/users/${id}/ban`,
  userUnban: (id) => `${API_PREFIX}/admin/users/${id}/unban`,
  userItem: (id) => `${API_PREFIX}/admin/users/${id}`,
  statsSummary: `${API_PREFIX}/admin/stats/summary`,
  statsDaily: (days = 7) => `${API_PREFIX}/admin/stats/daily?days=${days}`,
  statsItems: `${API_PREFIX}/admin/stats/items`,
  statsRanking: (limit = 5) => `${API_PREFIX}/admin/stats/ranking?limit=${limit}`,
  statsReports: `${API_PREFIX}/admin/stats/reports`,
};