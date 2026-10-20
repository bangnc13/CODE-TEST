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
:root{--ac:#0f766e;--ink:#0f2a26;--mut:#5b6f6a;--line:#cfe3de}
.block-container{padding:0!important;max-width:100%!important}
[data-testid="stMain"] iframe,section.main iframe{height:100vh!important;display:block;border:0}
[data-testid="stHeader"]{background:transparent}
[data-testid="stToolbar"],[data-testid="stDecoration"],footer{display:none!important}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#f3faf8,#e2f0ec);border-right:1px solid var(--line)}
@media(min-width:768px){[data-testid="stSidebar"]{min-width:370px!important;max-width:370px!important}}
.brand{display:flex;gap:12px;align-items:center;padding:16px;margin-bottom:10px;border-radius:18px;background:linear-gradient(135deg,#0f766e,#14b8a6);color:#fff;box-shadow:0 8px 20px #0f766e40}
.brand .logo{font-size:26px;width:46px;height:46px;border-radius:14px;background:#ffffff2b;display:grid;place-items:center}
.brand .t{font-weight:700;font-size:19px;letter-spacing:-.01em}.brand .s{font-size:12.5px;opacity:.92}
.step{display:flex;align-items:center;gap:10px;font-weight:700;color:var(--ink);margin:20px 0 8px}
.step i{font-style:normal;width:24px;height:24px;border-radius:50%;background:var(--ac);color:#fff;display:grid;place-items:center;font-size:12px}
.pill{display:inline-block;padding:3px 10px;border-radius:99px;background:#fff;border:1px solid var(--line);color:var(--mut);font-size:12px}
.pill.ok{background:#d9f4ee;border-color:#a8e0d4;color:#0b5c55}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0 8px}
.stat{background:#fff;border:1px solid var(--line);border-radius:14px;padding:10px 4px;text-align:center}
.stat b{display:block;font-size:22px;line-height:1.1;color:var(--ac)}.stat span{font-size:11.5px;color:var(--mut)}
[data-testid="stSidebar"] button,[data-testid^="stBaseLinkButton"]{border-radius:12px!important;font-weight:600}
[data-testid="stSidebar"] button[kind="primary"],[data-testid="stBaseButton-primary"]{background:linear-gradient(135deg,#0f766e,#14b8a6)!important;border:0!important;color:#fff!important;padding:.65rem 1rem;box-shadow:0 8px 18px #0f766e40}
[data-testid^="stBaseLinkButton"]{border:1.5px solid var(--ac)!important;background:#fff!important}
[data-testid^="stBaseLinkButton"] *{color:var(--ac)!important}
[data-testid^="stBaseLinkButton"]:hover{background:var(--ac)!important}
[data-testid^="stBaseLinkButton"]:hover *{color:#fff!important}
[data-testid="stFileUploaderDropzone"]{border:1.5px dashed var(--ac);background:#fff;border-radius:14px}
[data-testid="stSidebar"] input{border-radius:12px}
[data-testid="stSidebar"] [data-baseweb="select"]>div{border-radius:12px;max-height:150px;overflow-y:auto}
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

GEO = components.declare_component("geo_btn", path=str(Path(__file__).with_name("geo")))
step = lambda n, t: st.markdown(f'<div class="step"><i>{n}</i>{t}</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown(CSS + '<div class="brand"><div class="logo">🛵</div><div><div class="t">Lộ trình xe máy</div>'
                '<div class="s">Tối ưu theo đường bộ thật</div></div></div>', unsafe_allow_html=True)
    try:
        ROWS = load_sheet()
    except Exception:
        st.error("Không đọc được Google Sheet. Hãy chia sẻ file ở chế độ “Bất kỳ ai có đường liên kết đều xem được”.")
        st.stop()
    BYNAME = {v[0]: v for v in ROWS.values()}
    total = f"{len(BYNAME):,}".replace(",", ".")
    st.markdown(f'<span class="pill ok">{total} đối tượng có tọa độ</span>', unsafe_allow_html=True)

    step(1, "Đối tượng cần đi")
    up = st.file_uploader("Import Excel/CSV (cột “Tên đối tượng”)", type=["xlsx", "xls", "csv"])
    tpl = Path(__file__).with_name("Template.xlsx")
    if tpl.exists():
        st.download_button("⬇ Tải file mẫu", tpl.read_bytes(), "Template.xlsx", use_container_width=True)
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
    st.markdown(f'<span class="pill">Đã chọn {len(picked)} điểm</span>', unsafe_allow_html=True)

    step(2, "Điểm xuất phát")
    g = GEO(key="geo", default=None)
    start, src = ((g["lat"], g["lon"]), "gps") if g else (None, None)
    man = st.text_input("Hoặc nhập tọa độ (lat, lon)", placeholder="14.0123, 108.7654")
    if man and coord([man]):
        start, src = coord([man]), "man"
    if start:
        st.markdown(f'<span class="pill ok">{"📍 Vị trí hiện tại" if src == "gps" else "✍️ Nhập tay"}: {start[0]:.5f}, {start[1]:.5f}</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="pill">Chưa có vị trí · Google Maps sẽ đi từ vị trí hiện tại của máy</span>', unsafe_allow_html=True)

    step(3, "Lộ trình")
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
                        res, used = google(P, GKEY), "Google Routes API · xe máy"
                    except Exception as e:
                        st.warning(f"Google Routes lỗi, chuyển sang OSRM: {e}")
                if res is None:
                    try:
                        res, used = osrm(P), "OSRM · đường ô tô"
                    except Exception as e:
                        st.error(f"Không tính được lộ trình: {e}")
                        st.stop()
            st.session_state.res = dict(P=P, N=N, fb=fb, used=used, order=res[0], line=res[1], legs=res[2])

    R = st.session_state.get("res")
    if R:
        P, N, fb, order, line, legs = (R[k] for k in ("P", "N", "fb", "order", "line", "legs"))
        n_stop = len(order) - (0 if fb else 1)
        st.markdown(
            f'<div class="stats"><div class="stat"><b>{sum(l[0] for l in legs):.1f}</b><span>km</span></div>'
            f'<div class="stat"><b>{sum(l[1] for l in legs):.0f}</b><span>phút</span></div>'
            f'<div class="stat"><b>{n_stop}</b><span>điểm dừng</span></div></div>'
            f'<span class="pill ok">{R["used"]}</span>', unsafe_allow_html=True)
        # Mở Google Maps chế độ xe máy (mỗi liên kết tối đa 10 điểm dừng)
        stops, o = [P[i] for i in order[0 if fb else 1:]], (None if fb else P[0])
        for i in range(0, len(stops), 10):
            ch = stops[i:i + 10]
            d, w = ch[-1], ch[:-1]
            url = ("https://www.google.com/maps/dir/?api=1&travelmode=two-wheeler"
                   + (f"&origin={o[0]},{o[1]}" if o else "") + f"&destination={d[0]},{d[1]}"
                   + ("&waypoints=" + quote("|".join(f"{a},{b}" for a, b in w)) if w else ""))
            st.link_button(f"🗺 Mở Google Maps{f' · điểm {i + 1}–{i + len(ch)}' if len(stops) > 10 else ''}", url, use_container_width=True)
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
