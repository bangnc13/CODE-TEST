"""Lộ trình tối ưu cho xe máy: chạy trên Streamlit, đi theo đường bộ thật."""
import math, re, unicodedata
from pathlib import Path
from urllib.parse import quote

import folium
import pandas as pd
import polyline
import requests
import streamlit as st
from streamlit_folium import st_folium
from streamlit_geolocation import streamlit_geolocation

SHEET_ID = "1P7juPjYYReWhr9zQIyCg2PW_aTASA5dq1UG0DvfJUTk"
GID = "455030063"  # sheet "Tọa độ"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={GID}"

st.set_page_config(page_title="Lộ trình tối ưu xe máy", page_icon="🛵")


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
st.title("🛵 Lộ trình tối ưu cho xe máy")
try:
    ROWS = load_sheet()
except Exception:
    st.error("Không đọc được Google Sheet. Hãy chia sẻ file ở chế độ “Bất kỳ ai có đường liên kết đều xem được”.")
    st.stop()
BYNAME = {v[0]: v for v in ROWS.values()}
st.caption(f"Đã tải {len(BYNAME)} đối tượng có tọa độ từ sheet “Tọa độ”.")

st.subheader("1. Danh sách đối tượng cần đi")
up = st.file_uploader("Import danh sách (Excel/CSV, cột “Tên đối tượng”)", type=["xlsx", "xls", "csv"])
tpl = Path(__file__).with_name("Template.xlsx")
if tpl.exists():
    st.download_button("Tải file mẫu", tpl.read_bytes(), "Template.xlsx")
if up and st.session_state.get("tok") != (up.name, up.size):
    st.session_state.tok = (up.name, up.size)
    d = pd.read_csv(up, dtype=str) if up.name.lower().endswith(".csv") else pd.read_excel(up, dtype=str)
    col = next((c for c in d.columns if "ten doi tuong" in plain(c)), d.columns[0])
    names = [str(v).strip() for v in d[col].dropna() if str(v).strip()]
    st.session_state.sel = [ROWS[key(n)][0] for n in names if key(n) in ROWS]
    st.session_state.miss = [n for n in names if key(n) not in ROWS]
if st.session_state.get("miss"):
    st.warning("Không có trong sheet Tọa độ: " + ", ".join(st.session_state.miss[:30]))
st.multiselect("Chọn đối tượng", list(BYNAME), key="sel", placeholder="Gõ để tìm tên đối tượng")

st.subheader("2. Điểm xuất phát")
loc = streamlit_geolocation()
start = (loc["latitude"], loc["longitude"]) if loc and loc.get("latitude") else None
man = st.text_input("Hoặc nhập tọa độ xuất phát", placeholder="14.0123, 108.7654")
if man and coord([man]):
    start = coord([man])
st.caption(f"Xuất phát: {start[0]:.5f}, {start[1]:.5f}" if start else "Chưa có định vị: Google Maps sẽ xuất phát từ vị trí hiện tại của máy.")

if st.button("Tính lộ trình tối ưu", type="primary", use_container_width=True):
    chosen = [BYNAME[n] for n in st.session_state.get("sel", []) if n in BYNAME]
    fb = start is None
    P = ([] if fb else [start]) + [(c[1], c[2]) for c in chosen]
    N = ([] if fb else ["Vị trí xuất phát"]) + [c[0] for c in chosen]
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
    P, N, fb, order, line, legs = R["P"], R["N"], R["fb"], R["order"], R["line"], R["legs"]
    st.subheader("Kết quả")
    st.success(f"{len(order) - (0 if fb else 1)} điểm dừng · {sum(l[0] for l in legs):.1f} km · khoảng {sum(l[1] for l in legs):.0f} phút · {R['used']}")

    off = 1 if fb else 0  # số thứ tự hiển thị
    m = folium.Map(location=P[order[0]], zoom_start=14, tiles="OpenStreetMap")
    folium.PolyLine(line, color="#0f766e", weight=5, opacity=0.85).add_to(m)
    for k, i in enumerate(order):
        lab = "●" if (k == 0 and not fb) else k + off
        bg = "#c2410c" if lab == "●" else "#0f766e"
        folium.Marker(P[i], tooltip=N[i], icon=folium.DivIcon(
            icon_size=(26, 26), icon_anchor=(13, 13),
            html=f'<div style="width:26px;height:26px;border-radius:50%;background:{bg};color:#fff;border:2px solid #fff;display:grid;place-items:center;font:700 12px sans-serif">{lab}</div>')).add_to(m)
    m.fit_bounds([[min(p[0] for p in line), min(p[1] for p in line)], [max(p[0] for p in line), max(p[1] for p in line)]])
    st_folium(m, height=460, use_container_width=True, returned_objects=[])

    rows, cum = ([{"Thứ tự": 1, "Tên": N[order[0]], "Chặng (km)": 0, "Cộng dồn (km)": 0, "Phút": 0}] if fb else []), 0
    for k in range(1, len(order)):
        d, t = legs[k - 1]
        cum += d
        rows.append({"Thứ tự": k + off, "Tên": N[order[k]], "Chặng (km)": round(d, 2), "Cộng dồn (km)": round(cum, 2), "Phút": round(t)})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # Mở Google Maps chế độ xe máy (mỗi liên kết tối đa 10 điểm dừng)
    stops, o = [P[i] for i in order[0 if fb else 1:]], (None if fb else P[0])
    for i in range(0, len(stops), 10):
        ch = stops[i:i + 10]
        d, w = ch[-1], ch[:-1]
        url = ("https://www.google.com/maps/dir/?api=1&travelmode=two-wheeler"
               + (f"&origin={o[0]},{o[1]}" if o else "") + f"&destination={d[0]},{d[1]}"
               + ("&waypoints=" + quote("|".join(f"{a},{b}" for a, b in w)) if w else ""))
        st.link_button(f"Mở Google Maps (xe máy){f' · điểm {i + 1}–{i + len(ch)}' if len(stops) > 10 else ''}", url)
        o = d
