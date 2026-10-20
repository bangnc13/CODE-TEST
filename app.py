"""Lộ trình tối ưu cho xe máy: chạy trên Streamlit, đi theo đường bộ thật."""
import math, re, unicodedata
from pathlib import Path
from urllib.parse import quote

import json

import pandas as pd
import polyline
import requests
import streamlit as st
import streamlit.components.v1 as components
from streamlit_geolocation import streamlit_geolocation

SHEET_ID = "1P7juPjYYReWhr9zQIyCg2PW_aTASA5dq1UG0DvfJUTk"
GID = "455030063"  # sheet "Tọa độ"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={GID}"

st.set_page_config(page_title="Lộ trình tối ưu xe máy", page_icon="🛵", layout="wide", initial_sidebar_state="expanded")


# ---------- Đọc dữ liệu ----------
def plain(s):
    s = str(s).replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


def key(s):
    return re.sub(r"\s+", "", str(s)).upper()


PAIR = re.compile(r"(-?\d{1,3}[.,]\d{3,})\s*[,;/\s]\s*(-?\d{1,3}[.,]\d{3,})")
NUM = re.compile(r"\s*-?\d{1,3}[.,]\d{3,}\s*")


def fix(a, b):
    if abs(a) > 90:
        a, b = b, a
    return (a, b) if abs(a) <= 90 and abs(b) <= 180 else None


def coord(cells):
    """Tìm cặp (lat, lon) trong một dòng: 1 ô 'lat, lon' hoặc 2 ô số riêng."""
    for c in cells:
        m = PAIR.search(str(c))
        if m:
            return fix(*(float(x.replace(",", ".")) for x in m.groups()))
    n = [float(str(c).strip().replace(",", ".")) for c in cells if NUM.fullmatch(str(c))]
    return fix(n[0], n[1]) if len(n) > 1 else None


@st.cache_data(ttl=300, show_spinner="Đang tải Google Sheet…")
def load_sheet():
    df = pd.read_csv(CSV_URL, dtype=str, keep_default_na=False)
    h = [plain(c) for c in df.columns]
    nc = next((i for i, x in enumerate(h) if "ten doi tuong" in x), next((i for i, x in enumerate(h) if "ten" in x), 0))
    rows = {}
    for r in df.itertuples(index=False):
        name = str(r[nc]).strip()
        p = coord([v for i, v in enumerate(r) if i != nc])
        if name and p and key(name) not in rows:
            rows[key(name)] = (name, p[0], p[1])
    return rows


# ---------- Định tuyến theo đường bộ ----------
def hav(a, b):
    r = math.pi / 180
    x = math.sin((b[0] - a[0]) * r / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin((b[1] - a[1]) * r / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def osrm(P):
    """Miễn phí: OSRM Trip (tối ưu thứ tự, cố định điểm đầu) + hình học đường bộ."""
    c = ";".join(f"{lo},{la}" for la, lo in P)
    r = requests.get(
        f"https://router.project-osrm.org/trip/v1/driving/{c}",
        params=dict(source="first", roundtrip="false", geometries="geojson", overview="full"),
        timeout=60,
    ).json()
    if r.get("code") != "Ok":
        raise RuntimeError(r.get("message") or r.get("code"))
    wp, t = r["waypoints"], r["trips"][0]
    order = sorted(range(len(P)), key=lambda i: wp[i]["waypoint_index"])
    line = [(y, x) for x, y in t["geometry"]["coordinates"]]
    return order, line, [(l["distance"] / 1000, l["duration"] / 60) for l in t["legs"]]


def google(P, api_key):
    """Google Routes API, chế độ xe máy, tối ưu thứ tự điểm dừng (tối đa 25 điểm giữa)."""
    wp = lambda p: {"location": {"latLng": {"latitude": p[0], "longitude": p[1]}}}
    rest = P[1:]
    di = max(range(len(rest)), key=lambda i: hav(P[0], rest[i]))  # điểm xa nhất làm điểm cuối
    mid = [p for i, p in enumerate(rest) if i != di]
    body = {"origin": wp(P[0]), "destination": wp(rest[di]), "travelMode": "TWO_WHEELER"}
    if mid:
        body.update(intermediates=[wp(p) for p in mid], optimizeWaypointOrder=True)
    r = requests.post(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        json=body, timeout=60,
        headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": "routes.optimizedIntermediateWaypointIndex,routes.polyline.encodedPolyline,routes.legs.distanceMeters,routes.legs.duration"},
    )
    if not r.ok:
        raise RuntimeError(r.text[:200])
    rt = r.json()["routes"][0]
    oi = rt.get("optimizedIntermediateWaypointIndex", list(range(len(mid))))
    order = [0] + [1 + (j if j < di else j + 1) for j in oi] + [1 + di]
    legs = [(l.get("distanceMeters", 0) / 1000, float(str(l.get("duration", "0s")).rstrip("s")) / 60) for l in rt["legs"]]
    return order, polyline.decode(rt["polyline"]["encodedPolyline"]), legs


try:
    GKEY = st.secrets.get("GOOGLE_MAPS_API_KEY")
except Exception:
    GKEY = None

# ---------- Giao diện ----------
CSS = """<style>
.block-container{padding:0!important;max-width:100%!important}
[data-testid="stMain"] iframe,section.main iframe{height:100vh!important;display:block;border:0}
[data-testid="stHeader"]{background:transparent}
footer{visibility:hidden}
[data-testid="stSidebar"] [data-baseweb="select"]>div{max-height:150px;overflow-y:auto}
</style>"""

MAP_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>html,body,#m{height:100%;margin:0}.leaflet-top{margin-top:48px}
.pin{width:26px;height:26px;border-radius:50%;background:#0f766e;color:#fff;border:2px solid #fff;display:grid;place-items:center;font:700 12px sans-serif;box-shadow:0 1px 4px #0006}
.pin.s{background:#c2410c}</style></head><body><div id="m"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const D=__DATA__,map=L.map('m'),T=(u,o)=>L.tileLayer(u,{maxZoom:19,...o});
const esri='https://server.arcgisonline.com/ArcGIS/rest/services/';
const b={'Bản đồ đường':T(esri+'World_Street_Map/MapServer/tile/{z}/{y}/{x}',{attribution:'Tiles © Esri'}),
 'Vệ tinh':T(esri+'World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'Tiles © Esri'}),
 'OpenStreetMap':T('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap',referrerPolicy:'origin'})};
const a=b['Bản đồ đường'].addTo(map);L.control.layers(b).addTo(map);
let n=0;a.on('tileerror',()=>{if(++n==4){map.removeLayer(a);b['OpenStreetMap'].addTo(map)}});
const es=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const all=D.line.slice();
if(D.line.length)L.polyline(D.line,{color:'#0f766e',weight:5,opacity:.9}).addTo(map);
D.pts.forEach(p=>{all.push([p.lat,p.lng]);
 (p.l===''?L.circleMarker([p.lat,p.lng],{radius:6,color:'#fff',weight:2,fillColor:'#0f766e',fillOpacity:1})
 :L.marker([p.lat,p.lng],{icon:L.divIcon({className:'',iconSize:[26,26],html:'<div class="pin'+(p.s?' s':'')+'">'+es(p.l)+'</div>'})})).bindTooltip(es(p.n)).addTo(map)});
all.length>1?map.fitBounds(all,{padding:[60,60]}):all.length?map.setView(all[0],15):map.setView([16,107.5],6);
</script></body></html>"""

with st.sidebar:
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("### 🛵 Lộ trình tối ưu xe máy")
    try:
        ROWS = load_sheet()
    except Exception:
        st.error("Không đọc được Google Sheet. Hãy chia sẻ file ở chế độ “Bất kỳ ai có đường liên kết đều xem được”.")
        st.stop()
    BYNAME = {v[0]: v for v in ROWS.values()}
    st.caption(f"{len(BYNAME):,} đối tượng có tọa độ (sheet “Tọa độ”)")

    st.markdown("**1. Đối tượng cần đi**")
    up = st.file_uploader("Import danh sách (Excel/CSV, cột “Tên đối tượng”)", type=["xlsx", "xls", "csv"])
    tpl = Path(__file__).with_name("Template.xlsx")
    if tpl.exists():
        st.download_button("Tải file mẫu", tpl.read_bytes(), "Template.xlsx", use_container_width=True)
    if up and st.session_state.get("tok") != (up.name, up.size):
        st.session_state.tok = (up.name, up.size)
        d = pd.read_csv(up, dtype=str) if up.name.lower().endswith(".csv") else pd.read_excel(up, dtype=str)
        col = next((c for c in d.columns if "ten doi tuong" in plain(c)), d.columns[0])
        names = [str(v).strip() for v in d[col].dropna() if str(v).strip()]
        st.session_state.sel = [ROWS[key(n)][0] for n in names if key(n) in ROWS]
        st.session_state.miss = [n for n in names if key(n) not in ROWS]
    if st.session_state.get("miss"):
        st.warning("Không có trong sheet Tọa độ: " + ", ".join(st.session_state.miss[:30]))
    st.multiselect("Chọn từ danh sách", list(BYNAME), key="sel", placeholder="Gõ để tìm tên đối tượng")
    picked = [BYNAME[n] for n in st.session_state.get("sel", []) if n in BYNAME]

    st.markdown("**2. Điểm xuất phát**")
    loc = streamlit_geolocation()
    start = (loc["latitude"], loc["longitude"]) if loc and loc.get("latitude") else None
    man = st.text_input("Hoặc nhập tọa độ", placeholder="14.0123, 108.7654")
    if man and coord([man]):
        start = coord([man])
    st.caption(f"Xuất phát: {start[0]:.5f}, {start[1]:.5f}" if start else "Bấm nút định vị để dùng vị trí điện thoại. Nếu bỏ trống, Google Maps sẽ đi từ vị trí hiện tại của máy.")

    if st.button("Tính lộ trình tối ưu", type="primary", use_container_width=True):
        fb = start is None
        P = ([] if fb else [start]) + [(c[1], c[2]) for c in picked]
        N = ([] if fb else ["Vị trí xuất phát"]) + [c[0] for c in picked]
        if len(P) < 2:
            st.warning("Hãy chọn thêm đối tượng (hoặc bật định vị / nhập tọa độ xuất phát).")
        else:
            res = None
            with st.spinner("Đang tính lộ trình theo đường bộ…"):
                if GKEY and len(P) <= 27:
                    try:
                        res, used = google(P, GKEY), "Google Routes API (xe máy)"
                    except Exception as e:
                        st.warning(f"Google Routes lỗi, chuyển sang OSRM: {e}")
                if res is None:
                    try:
                        res, used = osrm(P), "OSRM (đường ô tô, miễn phí)"
                    except Exception as e:
                        st.error(f"Không tính được lộ trình: {e}")
                        st.stop()
            st.session_state.res = dict(P=P, N=N, fb=fb, used=used, order=res[0], line=res[1], legs=res[2])

    R = st.session_state.get("res")
    if R:
        P, N, fb, order, line, legs = (R[k] for k in ("P", "N", "fb", "order", "line", "legs"))
        st.divider()
        c1, c2 = st.columns(2)
        c1.metric("Quãng đường", f"{sum(l[0] for l in legs):.1f} km")
        c2.metric("Thời gian", f"{sum(l[1] for l in legs):.0f} phút")
        st.caption(f"{len(order) - (0 if fb else 1)} điểm dừng · {R['used']}")
        # Mở Google Maps chế độ xe máy (mỗi liên kết tối đa 10 điểm dừng)
        stops, o = [P[i] for i in order[0 if fb else 1:]], (None if fb else P[0])
        for i in range(0, len(stops), 10):
            ch = stops[i:i + 10]
            d, w = ch[-1], ch[:-1]
            url = ("https://www.google.com/maps/dir/?api=1&travelmode=two-wheeler"
                   + (f"&origin={o[0]},{o[1]}" if o else "") + f"&destination={d[0]},{d[1]}"
                   + ("&waypoints=" + quote("|".join(f"{a},{b}" for a, b in w)) if w else ""))
            st.link_button(f"Mở Google Maps (xe máy){f' · điểm {i + 1}–{i + len(ch)}' if len(stops) > 10 else ''}", url, use_container_width=True)
            o = d

# ---------- Bản đồ toàn màn hình ----------
if R:
    off = 0 if not R["fb"] else 1
    pts = [dict(lat=R["P"][i][0], lng=R["P"][i][1], n=R["N"][i], l="●" if (k == 0 and not R["fb"]) else str(k + off), s=(k == 0 and not R["fb"]))
           for k, i in enumerate(R["order"])]
    path = [list(p) for p in R["line"]]
else:  # chưa tính: hiện các điểm đã chọn
    pts = [dict(lat=c[1], lng=c[2], n=c[0], l="", s=False) for c in picked]
    if start:
        pts.append(dict(lat=start[0], lng=start[1], n="Vị trí xuất phát", l="●", s=True))
    path = []
components.html(MAP_HTML.replace("__DATA__", json.dumps({"pts": pts, "line": path}).replace("</", "<\\/")), height=700)
