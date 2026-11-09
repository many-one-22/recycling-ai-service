/**
 * nav.js - 모든 화면이 함께 쓰는 하단 내비게이션 바
 *
 * 쓰는 법: 모바일 컨테이너 맨 아래에 <div id="bottomNav"></div> 를 두고
 *          </body> 앞에서 이 파일을 불러오면 된다. nav.css 도 같이 필요하다.
 *
 * 한 군데(NAV_ITEMS)만 고치면 네 화면에 모두 반영된다.
 * 현재 보고 있는 화면은 자동으로 초록색(active)으로 표시된다.
 */

const NAV_ITEMS = [
  {
    label: '홈',
    icon: '🏠',
    href: '/fe-ui/index.html',
    // 이 주소들 중 하나면 '현재 화면'으로 본다 (/ 는 index.html 과 같은 화면)
    paths: ['/', '/fe-ui/index.html']
  },
  {
    label: '수거함 위치',
    icon: '📍',
    href: '/fe-map/map_index.html',
    paths: ['/map', '/fe-map/map_index.html']
  },
  {
    label: '환경 퀴즈',
    icon: '🌱',
    href: '/fe-quiz/quiz_index.html',
    paths: ['/quiz', '/fe-quiz/quiz_index.html']
  },
  {
    label: '마이페이지',
    icon: '👤',
    href: '/fe-ui/my_page.html',
    // 로그인 안 했으면 로그인 화면으로 보낸다
    hrefWhenLoggedOut: '/fe-ui/sign_in.html',
    paths: ['/fe-ui/my_page.html', '/fe-ui/sign_in.html', '/fe-ui/admin.html']
  }
];

function isLoggedIn() {
  try {
    return !!localStorage.getItem('access_token');
  } catch (e) {
    // 사생활 보호 모드 등에서 localStorage 가 막혀도 바는 떠야 한다
    return false;
  }
}

function renderBottomNav() {
  const mount = document.getElementById('bottomNav');
  if (!mount) return;

  const current = window.location.pathname;
  const loggedIn = isLoggedIn();

  const nav = document.createElement('nav');
  nav.className = 'bottom-nav';

  NAV_ITEMS.forEach((item) => {
    const a = document.createElement('a');
    a.className = 'nav-item';
    a.href = (!loggedIn && item.hrefWhenLoggedOut) ? item.hrefWhenLoggedOut : item.href;

    if (item.paths.includes(current)) {
      a.classList.add('active');
    }

    const icon = document.createElement('span');
    icon.className = 'icon';
    icon.textContent = item.icon;

    const label = document.createElement('span');
    label.className = 'label';
    label.textContent = item.label;

    a.appendChild(icon);
    a.appendChild(label);
    nav.appendChild(a);
  });

  mount.replaceWith(nav);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', renderBottomNav);
} else {
  renderBottomNav();
}
