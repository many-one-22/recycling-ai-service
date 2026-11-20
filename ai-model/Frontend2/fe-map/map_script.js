let map = null;
let centerMarkers = [];
let myLocationOverlay = null;

let centerData = [];
let exchangeRulesData = [];
let sourcesData = [];

const DEFAULT_LAT = 35.1595454;
const DEFAULT_LNG = 126.8526012;

document.addEventListener("DOMContentLoaded", () => {
    initMap();
    loadInitialData();
});

function initMap() {
    const container = document.getElementById('map');
    const options = {
        center: new kakao.maps.LatLng(DEFAULT_LAT, DEFAULT_LNG),
        level: 7
    };
    map = new kakao.maps.Map(container, options);
}

// 초기 데이터 로드 (백엔드 API 연결)
async function loadInitialData() {
    // 초기/목업 데이터
    centerData = [
        { 
            id: 1, 
            gu: "서구", 
            name: "치평동행정복지센터", 
            address: "광주광역시 서구 시청로 30", 
            lat: 35.1534, 
            lng: 126.8482, 
            phone: "062-360-7000", 
            items: "폐건전지;아이스팩;종이팩", 
            items_unverified: "투명페트병", 
            sources: "SEO_PAGE" 
        }
    ];

    exchangeRulesData = [
        { gu: "서구", item: "폐건전지", rule: "10개 → 새건전지 2개", limit: "1회 방문 시 최대 100개" },
        { gu: "서구", item: "종이팩", rule: "1kg → 종량제봉투(20L) 1매", limit: null }
    ];

    sourcesData = [
        { source_id: "SEO_PAGE", title: "서구 – 재활용품 수거 안내", url: "https://www.seogu.gwangju.kr" }
    ];

    renderMarkers(centerData);
    updateChipStates();

    try {
        const [centersRes, rulesRes, sourcesRes] = await Promise.all([
            fetch('/api/centers'),
            fetch('/api/exchange-rules'),
            fetch('/api/sources')
        ]);

        if (centersRes.ok) {
            const serverCenters = await centersRes.json();
            if (serverCenters && serverCenters.length > 0) {
                centerData = serverCenters;
                renderMarkers(centerData);
                updateChipStates();
            }
        }
        if (rulesRes.ok) exchangeRulesData = await rulesRes.json();
        if (sourcesRes.ok) sourcesData = await sourcesRes.json();

    } catch (e) {
        console.log("백엔드 미연결 상태: 목업 데이터 사용 중");
    }
}

// -------------------------------------------------------------
// 품목 칩 상태 갱신
//   수거함 데이터가 실제로 있는 품목만 누를 수 있게 한다.
//   데이터가 없는 칩을 그냥 두면, 눌렀을 때 빈 지도가 떠서 고장처럼 보인다.
// -------------------------------------------------------------
function availableCategories(data) {
    const set = new Set();
    data.forEach(item => {
        if (!item.items) return;
        const list = typeof item.items === 'string'
            ? item.items.split(';').map(i => i.trim())
            : item.items;
        list.forEach(i => { if (i) set.add(i); });
    });
    return set;
}

function updateChipStates() {
    const available = availableCategories(centerData);

    document.querySelectorAll('.chip').forEach(chip => {
        const category = chip.getAttribute('data-category');
        if (category === '전체') return;

        const count = category && available.has(category)
            ? centerData.filter(it => {
                  const list = typeof it.items === 'string'
                      ? it.items.split(';').map(i => i.trim())
                      : (it.items || []);
                  return list.includes(category);
              }).length
            : 0;

        if (count > 0) {
            chip.classList.remove('chip-empty');
            chip.removeAttribute('title');
        } else {
            chip.classList.add('chip-empty');
            chip.setAttribute('title', '아직 확인된 수거함 데이터가 없습니다');
        }
    });
}

// 잠깐 떴다 사라지는 안내 메시지
function showHint(message) {
    let el = document.getElementById('map-hint');
    if (!el) {
        el = document.createElement('div');
        el.id = 'map-hint';
        el.className = 'map-hint';
        document.querySelector('.app-layout').appendChild(el);
    }
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(showHint._timer);
    showHint._timer = setTimeout(() => el.classList.remove('show'), 2200);
}

// 지도 마커 표시
function renderMarkers(data) {
    clearMarkers();

    data.forEach(item => {
        if (!item.lat || !item.lng) return;

        const pos = new kakao.maps.LatLng(item.lat, item.lng);
        const marker = new kakao.maps.Marker({
            position: pos,
            map: map
        });

        kakao.maps.event.addListener(marker, 'click', () => {
            openBottomSheet(item);
        });

        centerMarkers.push(marker);
    });
}

function clearMarkers() {
    centerMarkers.forEach(m => m.setMap(null));
    centerMarkers = [];
}

// 위치 및 센터 검색
function searchLocation() {
    const keyword = document.getElementById('search-input').value.trim();
    if (!keyword) {
        alert("검색어를 입력해 주세요.");
        return;
    }

    // 1. 센터 데이터 검색 (gu, name, address 기준)
    const matchedCenter = centerData.find(c => 
        (c.name && c.name.includes(keyword)) || 
        (c.address && c.address.includes(keyword)) || 
        (c.gu && c.gu.includes(keyword))
    );

    if (matchedCenter) {
        const moveLatLon = new kakao.maps.LatLng(matchedCenter.lat, matchedCenter.lng);
        map.setLevel(4);
        map.panTo(moveLatLon);
        openBottomSheet(matchedCenter);
        return;
    }

    // 2. 카카오 장소 검색 API 활용
    const ps = new kakao.maps.services.Places();
    ps.keywordSearch(`광주 ${keyword}`, (data, status) => {
        if (status === kakao.maps.services.Status.OK) {
            const bounds = new kakao.maps.LatLngBounds();
            bounds.extend(new kakao.maps.LatLng(data[0].y, data[0].x));
            map.setBounds(bounds);
        } else {
            alert("검색 결과를 찾을 수 없습니다.");
        }
    });
}

// 품목 필터ing (문자열 세미콜론 구분)
function onFilterClick(button) {
    // 데이터가 없는 품목은 지도를 비우지 않고 안내만 띄운다
    if (button.classList.contains('chip-empty')) {
        showHint(`${button.getAttribute('data-category')} 수거함은 아직 확인된 데이터가 없어요`);
        return;
    }

    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    button.classList.add('active');

    const category = button.getAttribute('data-category');

    if (category === '전체') {
        renderMarkers(centerData);
    } else {
        const filtered = centerData.filter(item => {
            if (!item.items) return false;
            // items가 세미콜론(;)으로 구분된 문자열인 경우 처리
            const itemList = typeof item.items === 'string' 
                ? item.items.split(';').map(i => i.trim()) 
                : item.items;
            return itemList.includes(category);
        });
        renderMarkers(filtered);
    }
}

// 내 위치 이동
function moveToCurrentLocation() {
    if (!navigator.geolocation) {
        alert("위치 서비스를 지원하지 않는 브라우저입니다.");
        return;
    }

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            const loc = new kakao.maps.LatLng(lat, lng);

            if (myLocationOverlay) {
                myLocationOverlay.setMap(null);
            }

            const content = `
                <div class="my-location-marker">
                    <div class="core"></div>
                    <div class="pulse"></div>
                </div>
            `;

            myLocationOverlay = new kakao.maps.CustomOverlay({
                map: map,
                position: loc,
                content: content,
                yAnchor: 0.5,
                xAnchor: 0.5
            });

            map.setLevel(4);
            map.panTo(loc);
        },
        () => {
            alert("현재 위치를 불러올 수 없습니다.");
        }
    );
}

// 상세 정보 바텀시트 모달
function openBottomSheet(center) {
    // gu, phone, items, items_unverified 데이터 규격 적용
    document.getElementById('sheet-gu-badge').innerText = `${center.gu || '광주'} 행정복지센터`;
    document.getElementById('sheet-title').innerText = center.name;
    document.getElementById('sheet-address').innerText = center.address || '주소 정보 없음';
    document.getElementById('sheet-phone').innerText = center.phone ? `전화: ${center.phone}` : '전화번호 정보 없음';

    // 수거 가능 품목 (items: "폐건전지;아이스팩;종이팩")
    const itemsContainer = document.getElementById('sheet-items');
    itemsContainer.innerHTML = '';
    
    if (center.items) {
        const itemList = typeof center.items === 'string' ? center.items.split(';') : center.items;
        itemList.forEach(item => {
            if (item.trim()) {
                const badge = document.createElement('span');
                badge.className = 'item-badge';
                badge.innerText = item.trim();
                itemsContainer.appendChild(badge);
            }
        });
    }

    // 미확인 품목 (items_unverified)
    const unverifiedBox = document.getElementById('unverified-box');
    const unverifiedText = document.getElementById('unverified-items-text');

    if (center.items_unverified && center.items_unverified.trim()) {
        const unverifiedList = center.items_unverified.replace(/;/g, ', ');
        unverifiedText.innerText = `[${unverifiedList}] 품목은 센터 문의 후 방문하세요.`;
        unverifiedBox.style.display = 'block';
    } else {
        unverifiedBox.style.display = 'none';
    }

    // 구별 보상 교환 기준 (/api/exchange-rules)
    const exchangeBox = document.getElementById('exchange-rules-box');
    const exchangeList = document.getElementById('exchange-rules-list');
    
    if (exchangeBox && exchangeList) {
        const rules = exchangeRulesData.filter(r => r.gu === center.gu);
        exchangeList.innerHTML = '';

        if (rules.length > 0) {
            rules.forEach(r => {
                const li = document.createElement('li');
                li.innerText = `• ${r.item}: ${r.rule} ${r.limit ? `(${r.limit})` : ''}`;
                exchangeList.appendChild(li);
            });
            exchangeBox.style.display = 'block';
        } else {
            exchangeBox.style.display = 'none';
        }
    }

    document.getElementById('bottom-sheet').classList.add('show');
}

function closeBottomSheet() {
    document.getElementById('bottom-sheet').classList.remove('show');
}

// -------------------------------------------------------------
// 품목 칩 줄을 마우스로 끌어서 스크롤
//   터치(휴대폰)는 기본으로 되지만, 데스크톱 마우스는 드래그가 안 된다.
//   발표 때 노트북으로 시연하므로 마우스로도 끌 수 있게 한다.
// -------------------------------------------------------------
function enableDragScroll(el) {
    if (!el) return;
    let down = false, startX = 0, startScroll = 0, moved = 0;

    el.addEventListener('mousedown', (e) => {
        down = true; moved = 0;
        startX = e.pageX;
        startScroll = el.scrollLeft;
        el.classList.add('dragging');
    });

    const stop = () => { down = false; el.classList.remove('dragging'); };
    el.addEventListener('mouseleave', stop);
    window.addEventListener('mouseup', stop);

    el.addEventListener('mousemove', (e) => {
        if (!down) return;
        e.preventDefault();
        const dx = e.pageX - startX;
        moved = Math.abs(dx);
        el.scrollLeft = startScroll - dx;
    });

    // 끌어서 움직인 뒤에는 칩이 눌리지 않게 막는다
    el.addEventListener('click', (e) => {
        if (moved > 5) { e.stopPropagation(); e.preventDefault(); }
    }, true);

    // 세로 휠로도 가로 스크롤
    el.addEventListener('wheel', (e) => {
        if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
            el.scrollLeft += e.deltaY;
            e.preventDefault();
        }
    }, { passive: false });
}

document.addEventListener('DOMContentLoaded', () => {
    enableDragScroll(document.querySelector('.filter-scroll'));
});
