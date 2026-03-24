"""
歸程隊C隊點名系統 — Streamlit
Live QR 碼掃描（無需按快門）+ 即時點名
"""

import base64
import csv
import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st
import streamlit.components.v1 as stcomponents

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="歸程隊C隊 點名",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden; height: 0; }
.stDeployButton, [data-testid="stToolbar"] { display: none !important; }
.stApp { background: #f0f4f8; }
.block-container { padding: 0.75rem 1.25rem 3rem !important; max-width: 860px !important; }

.stTabs [data-baseweb="tab-list"] {
  background: white; border-radius: 14px; padding: 5px; gap: 3px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.09);
}
.stTabs [data-baseweb="tab"] {
  border-radius: 9px; font-weight: 700; padding: 9px 16px;
  font-size: 0.86rem; color: #64748b;
}
.stTabs [aria-selected="true"] {
  background: linear-gradient(135deg, #2563eb, #4f46e5) !important;
  color: white !important;
  box-shadow: 0 2px 8px rgba(37,99,235,0.35);
}

.stButton > button {
  border-radius: 11px !important; font-weight: 700 !important;
  transition: all 0.15s !important; font-size: 0.85rem !important;
}
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #2563eb, #4f46e5) !important;
  border: none !important;
  box-shadow: 0 2px 8px rgba(37,99,235,0.3) !important;
}
.stButton > button:hover { transform: translateY(-1px) !important; }

.stTextInput > div > div > input {
  border-radius: 11px !important; border: 1.5px solid #e2e8f0 !important;
  background: white !important; padding: 10px 14px !important; font-size: 0.9rem !important;
}
.stTextInput > div > div > input:focus {
  border-color: #2563eb !important;
  box-shadow: 0 0 0 3px rgba(37,99,235,0.12) !important;
}
.stSelectbox > div > div { border-radius: 11px !important; }
.stProgress > div > div > div {
  background: linear-gradient(90deg,#2563eb,#7c3aed) !important;
  border-radius: 999px !important;
}
.stDownloadButton > button { border-radius: 11px !important; font-weight: 700 !important; }
.stAlert { border-radius: 12px !important; }
hr { border-color: #e2e8f0 !important; margin: 6px 0 !important; }
div[data-testid="stFormSubmitButton"] > button {
  border-radius: 11px !important; font-weight: 700 !important;
  background: linear-gradient(135deg, #2563eb, #4f46e5) !important;
  border: none !important; color: white !important;
}
</style>
""", unsafe_allow_html=True)

# ── Password gate ──────────────────────────────────────────────────────────────
_PWD = "ktps"
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                min-height:78vh;">
      <div style="background:linear-gradient(135deg,#1e40af,#2563eb);
                  width:80px;height:80px;border-radius:24px;display:flex;align-items:center;
                  justify-content:center;font-size:2.4rem;
                  box-shadow:0 8px 30px rgba(37,99,235,0.4);margin-bottom:20px;">✅</div>
      <h2 style="color:#1e293b;font-size:1.6rem;font-weight:800;margin-bottom:4px;">歸程隊C隊</h2>
      <p style="color:#64748b;font-size:.9rem;margin-bottom:8px;">點名系統</p>
    </div>
    """, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        pwd = st.text_input("密碼", type="password", label_visibility="collapsed",
                            placeholder="🔒  輸入密碼…")
        if st.button("登入", use_container_width=True, type="primary"):
            if pwd == _PWD:
                st.session_state.auth = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤")
    st.stop()

# ── Firebase ───────────────────────────────────────────────────────────────────
@st.cache_resource
def _init_db():
    if not firebase_admin._apps:
        try:
            if "FIREBASE_JSON_B64" in st.secrets:
                d = json.loads(base64.b64decode(st.secrets["FIREBASE_JSON_B64"]).decode())
            elif "FIREBASE_SERVICE_ACCOUNT" in st.secrets:
                raw = st.secrets["FIREBASE_SERVICE_ACCOUNT"]
                d = json.loads(raw) if isinstance(raw, str) else dict(raw)
            else:
                return None, "找不到 Firebase secret"
            firebase_admin.initialize_app(credentials.Certificate(d))
        except Exception as e:
            return None, str(e)
    return firestore.client(), None

_db, _db_err = _init_db()
if _db is None:
    st.error(f"❌ Firebase 連線失敗：{_db_err}")
    st.stop()
db = _db

# ── Live QR scanner component ──────────────────────────────────────────────────
@st.cache_resource
def _qr_comp():
    return stcomponents.declare_component(
        "qr_live",
        path=str(Path(__file__).parent / "components" / "qr_scanner"),
    )

_qr_widget = _qr_comp()

def live_qr(key="qr"):
    return _qr_widget(key=key, default=None)

# ── Helpers ────────────────────────────────────────────────────────────────────
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def today_label():
    n = datetime.now()
    return f"{n.year}年{n.month}月{n.day}日　{WEEKDAYS[n.weekday()]}"

@st.cache_data(ttl=8)
def load_students():
    return sorted(
        [d.to_dict() for d in db.collection("students").stream()],
        key=lambda s: (s.get("class", ""), int(s.get("number") or 0))
    )

@st.cache_data(ttl=5)
def load_records(date: str):
    snap = db.collection("daily_records").document(date).get()
    return snap.to_dict().get("records", {}) if snap.exists else {}

@st.cache_data(ttl=30)
def load_dates():
    return sorted([d.id for d in db.collection("daily_records").stream()], reverse=True)

def _clear():
    load_students.clear()
    load_records.clear()
    load_dates.clear()

def set_status(student, new_status):
    td = today_str()
    now = datetime.now()
    db.collection("daily_records").document(td).set({
        "date": td, "timestamp": now.timestamp(),
        "records": {student["id"]: {
            "status": new_status,
            "time": now.strftime("%H:%M") if new_status == "present" else None,
            "name": student["name"],
            "class": student.get("class", ""),
            "number": student.get("number", ""),
        }}
    }, merge=True)
    _clear()

def set_note(student, note):
    td = today_str()
    now = datetime.now()
    db.collection("daily_records").document(td).set({
        "date": td, "timestamp": now.timestamp(),
        "records": {student["id"]: {
            "dailyNote": note,
            "name": student["name"],
            "class": student.get("class", ""),
            "number": student.get("number", ""),
        }}
    }, merge=True)
    _clear()

def merge(students, records):
    return [{
        **s,
        "status":    "present" if records.get(s["id"], {}).get("status") == "present" else "absent",
        "time":      records.get(s["id"], {}).get("time", ""),
        "dailyNote": records.get(s["id"], {}).get("dailyNote", ""),
    } for s in students]

def make_csv(data, date):
    buf = io.StringIO()
    buf.write(f"日期：{date}\n")
    w = csv.writer(buf)
    w.writerow(["班級", "學號", "姓名", "狀態", "報到時間", "今日通報", "備註(跟隨)", "活動"])
    for s in data:
        acts = "、".join(s.get("activities") or [])
        w.writerow([s.get("class", ""), s.get("number", ""), s.get("name", ""),
                    "已到" if s.get("status") == "present" else "未到",
                    s.get("time", ""), s.get("dailyNote", ""), s.get("notes", ""), acts])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")

def process_qr(qr_text, computed):
    name = qr_text.strip()
    match = next((s for s in computed if s["name"] == name or s["id"] == name), None)
    if not match:
        return None, f"找不到學生：{name}", False
    if match["status"] == "present":
        return match, f"{match['name']} 已報到（{match['time']}）", False
    set_status(match, "present")
    return match, f"✅  {match['name']} 報到成功！", True

# ── Session defaults ───────────────────────────────────────────────────────────
for k, v in [("last_scan_ts", 0), ("scan_result", None), ("note_editing", {})]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Data ───────────────────────────────────────────────────────────────────────
td        = today_str()
students  = load_students()
records   = load_records(td)
computed  = merge(students, records)
present_n = sum(1 for s in computed if s["status"] == "present")
total_n   = len(computed)
pct       = int(present_n / total_n * 100) if total_n else 0

# ── Header ─────────────────────────────────────────────────────────────────────
h_col, ref_col = st.columns([10, 1])
with h_col:
    st.markdown(f"""
<div style="background:linear-gradient(135deg,#1e3a8a 0%,#2563eb 55%,#3b82f6 100%);
            border-radius:18px;padding:20px 26px;color:white;margin-bottom:14px;
            box-shadow:0 6px 24px rgba(37,99,235,0.32);
            display:flex;justify-content:space-between;align-items:center;">
  <div>
    <div style="font-size:1.4rem;font-weight:800;letter-spacing:-.3px;">🏃 歸程隊C隊　點名系統</div>
    <div style="font-size:.82rem;opacity:.8;margin-top:3px;">{today_label()}</div>
    <div style="margin-top:11px;background:rgba(255,255,255,.18);border-radius:999px;height:5px;width:150px;">
      <div style="background:#22d3ee;border-radius:999px;height:5px;width:{pct}%;"></div>
    </div>
    <div style="font-size:.72rem;opacity:.7;margin-top:3px;">出席率 {pct}%</div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:2.9rem;font-weight:800;line-height:1;text-shadow:0 2px 8px rgba(0,0,0,.2);">
      {present_n}<span style="font-size:1.3rem;opacity:.6;">/{total_n}</span>
    </div>
    <div style="font-size:.72rem;opacity:.7;margin-top:2px;">已到 / 總人數</div>
  </div>
</div>
""", unsafe_allow_html=True)
with ref_col:
    st.markdown("<div style='padding-top:16px'></div>", unsafe_allow_html=True)
    if st.button("🔄", help="重新整理"):
        _clear(); st.rerun()

# ── Student card ───────────────────────────────────────────────────────────────
def _student_card(s, key_prefix=""):
    is_p   = s["status"] == "present"
    bg     = "#f0fdf4" if is_p else "white"
    border = "#bbf7d0" if is_p else "#e2e8f0"
    left   = "#16a34a" if is_p else "#cbd5e1"
    icon   = "✅" if is_p else "⬜"

    time_html  = f'<span style="font-size:.78rem;color:#16a34a;margin-left:6px;">🕐 {s["time"]}</span>' if s.get("time") else ""
    notes_html = f'<div style="font-size:.78rem;color:#2563eb;margin-top:3px;">👨‍👧 {s["notes"]}</div>' if s.get("notes") else ""

    acts_html = "".join(
        f'<span style="display:inline-block;background:#ede9fe;color:#6d28d9;border-radius:6px;'
        f'padding:1px 8px;font-size:.72rem;margin:2px 2px 0 0;">{a}</span>'
        for a in (s.get("activities") or [])
    )
    acts_wrap = f'<div style="margin-top:5px;">{acts_html}</div>' if acts_html else ""

    note_badge = (
        f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;'
        f'padding:5px 10px;margin-top:6px;font-size:.8rem;color:#b91c1c;display:flex;gap:6px;">'
        f'<span>📢</span><span>{s["dailyNote"]}</span></div>'
    ) if s.get("dailyNote") else ""

    st.markdown(f"""
<div style="background:{bg};border:1px solid {border};border-left:4px solid {left};
            border-radius:12px;padding:10px 14px;
            box-shadow:0 1px 3px rgba(0,0,0,.05);">
  <span style="font-size:1.05rem;font-weight:700;color:#1e293b;">{icon} {s['name']}</span>{time_html}
  <div style="margin-top:3px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
    <span style="background:#e2e8f0;border-radius:6px;padding:1px 8px;font-size:.75rem;color:#475569;font-weight:600;">{s.get('class', '')}</span>
    <span style="font-size:.8rem;color:#64748b;">{s.get('number', '')}號</span>
  </div>
  {notes_html}{acts_wrap}{note_badge}
</div>
""", unsafe_allow_html=True)

    btn_c, note_c = st.columns(2)
    with btn_c:
        lbl  = "↩️ 取消報到" if is_p else "✅ 報到"
        kind = "secondary" if is_p else "primary"
        if st.button(lbl, key=f"{key_prefix}a_{s['id']}", use_container_width=True, type=kind):
            set_status(s, "absent" if is_p else "present")
            st.rerun()
    with note_c:
        nlbl = "✏️ 編輯通報" if s.get("dailyNote") else "📝 通報"
        if st.button(nlbl, key=f"{key_prefix}n_{s['id']}", use_container_width=True):
            k2 = f"ne_{s['id']}"
            st.session_state.note_editing[k2] = not st.session_state.note_editing.get(k2, False)

    if st.session_state.note_editing.get(f"ne_{s['id']}"):
        with st.form(key=f"{key_prefix}f_{s['id']}"):
            st.caption(f"📢 今日通報 — {s.get('class', '')} {s['name']}")
            nv = st.text_area("備註", value=s.get("dailyNote", ""),
                              placeholder="家長接回 / 早退 / 病假 / 自行放學…",
                              height=70, label_visibility="collapsed")
            st.caption("快速：`家長接回`  `早退`  `病假/事假`  `自行放學`")
            sc2, cc2 = st.columns(2)
            if sc2.form_submit_button("💾 儲存", type="primary", use_container_width=True):
                set_note(s, nv.strip())
                st.session_state.note_editing[f"ne_{s['id']}"] = False
                st.rerun()
            if cc2.form_submit_button("取消", use_container_width=True):
                st.session_state.note_editing[f"ne_{s['id']}"] = False
                st.rerun()

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab_scan, tab_list, tab_history, tab_settings = st.tabs(
    ["📷 掃描點名", "📋 今日名單", "📅 歷史紀錄", "⚙️ 設定"]
)

# ─────────────────────────── TAB: 掃描點名 ────────────────────────────────────
with tab_scan:
    left_col, right_col = st.columns([1, 1], gap="large")

    with left_col:
        st.markdown(
            '<div style="font-size:.9rem;font-weight:700;color:#1e293b;margin-bottom:6px;">📷 Live QR 掃描</div>',
            unsafe_allow_html=True
        )

        # Live QR component — auto-scans, no button needed
        scan_result = live_qr(key="qr_main")

        # Process a new scan
        if scan_result and isinstance(scan_result, dict):
            ts = scan_result.get("ts", 0)
            if ts and ts != st.session_state.last_scan_ts:
                st.session_state.last_scan_ts = ts
                student, msg, success = process_qr(scan_result.get("text", ""), computed)
                st.session_state.scan_result = {"student": student, "msg": msg, "success": success}
                st.rerun()

        # Last scan result card
        if st.session_state.scan_result:
            r = st.session_state.scan_result
            s = r["student"]
            if r["success"] and s:
                acts_text = "　".join(s.get("activities") or [])
                acts_row  = f'<div style="font-size:.78rem;color:#7c3aed;margin-top:3px;">🏃 {acts_text}</div>' if acts_text else ""
                note_row  = (
                    f'<div style="font-size:.78rem;color:#b91c1c;background:#fef2f2;'
                    f'border-radius:6px;padding:3px 8px;margin-top:4px;">📢 {s["dailyNote"]}</div>'
                ) if s.get("dailyNote") else ""
                st.markdown(f"""
<div style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);border:1.5px solid #86efac;
            border-radius:14px;padding:14px 16px;margin-top:10px;
            box-shadow:0 3px 12px rgba(22,163,74,.15);">
  <div style="font-size:.72rem;color:#16a34a;font-weight:700;letter-spacing:.5px;margin-bottom:6px;">✅  SCANNED</div>
  <div style="font-size:1.4rem;font-weight:800;color:#14532d;">{s['name']}</div>
  <div style="font-size:.82rem;color:#166534;margin-top:2px;">{s.get('class', '')}　{s.get('number', '')}號</div>
  {acts_row}{note_row}
  <div style="font-size:.75rem;color:#16a34a;margin-top:6px;opacity:.8;">{datetime.now().strftime('%H:%M')} 報到成功</div>
</div>
""", unsafe_allow_html=True)
            else:
                colour = "#dc2626" if not r["success"] else "#2563eb"
                icon2  = "⚠️" if not r["success"] else "ℹ️"
                st.markdown(f"""
<div style="background:#fef2f2;border:1.5px solid #fca5a5;border-radius:14px;
            padding:14px 16px;margin-top:10px;">
  <div style="font-size:.88rem;font-weight:700;color:{colour};">{icon2}  {r['msg']}</div>
</div>
""", unsafe_allow_html=True)

    with right_col:
        st.markdown(
            '<div style="font-size:.9rem;font-weight:700;color:#1e293b;margin-bottom:6px;">🔍 手動搜尋點名</div>',
            unsafe_allow_html=True
        )
        manual = st.text_input("手動", placeholder="姓名 / 班級+號 …",
                               label_visibility="collapsed", key="manual_q")
        if manual:
            q = manual.strip().lower()
            hits = [s for s in computed
                    if q in s["name"].lower()
                    or q in s.get("class", "").lower()
                    or str(s.get("number", "")) == q
                    or (s.get("class", "").lower() + str(s.get("number", ""))) == q]
            if hits:
                for m in hits[:8]:
                    is_p2    = m["status"] == "present"
                    time_tag = (
                        f'<span style="float:right;font-size:.75rem;color:#16a34a;">✅ {m["time"]}</span>'
                        if is_p2 else ""
                    )
                    bg2  = "#f0fdf4" if is_p2 else "white"
                    bdr2 = "#bbf7d0" if is_p2 else "#e2e8f0"
                    st.markdown(f"""
<div style="background:{bg2};border:1px solid {bdr2};border-radius:10px;
            padding:8px 12px;margin-bottom:2px;">
  <span style="font-weight:700;">{m['name']}</span>
  <span style="font-size:.8rem;color:#64748b;margin-left:8px;">{m.get('class', '')} {m.get('number', '')}號</span>
  {time_tag}
</div>
""", unsafe_allow_html=True)
                    if st.button(
                        "↩️ 取消" if is_p2 else "✅ 報到",
                        key=f"m_{m['id']}", use_container_width=True,
                        type="secondary" if is_p2 else "primary"
                    ):
                        set_status(m, "absent" if is_p2 else "present")
                        st.rerun()
            else:
                st.caption("❌ 找不到符合的學生")

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:.9rem;font-weight:700;color:#1e293b;margin-bottom:6px;">🕐 最近報到</div>',
            unsafe_allow_html=True
        )
        recent = sorted(
            [s for s in computed if s["status"] == "present" and s.get("time")],
            key=lambda s: s.get("time", ""), reverse=True
        )[:8]
        if recent:
            for s in recent:
                st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:center;
            padding:7px 12px;background:white;border-radius:9px;margin-bottom:3px;
            border:1px solid #e2e8f0;">
  <span style="font-weight:700;font-size:.88rem;">{s['name']}</span>
  <span style="font-size:.75rem;color:#64748b;">{s.get('class', '')} {s.get('number', '')}號</span>
  <span style="font-size:.75rem;color:#16a34a;font-weight:600;">🕐 {s['time']}</span>
</div>
""", unsafe_allow_html=True)
        else:
            st.caption("暫無報到紀錄")

# ─────────────────────────── TAB: 今日名單 ────────────────────────────────────
with tab_list:
    if not students:
        st.info("🗂️ 雲端尚無學生資料，請前往「設定」上傳 CSV 名單。")
    else:
        fc1, fc2 = st.columns([3, 1])
        with fc1:
            search = st.text_input("搜尋", placeholder="搜尋班級或姓名…",
                                   label_visibility="collapsed", key="list_search")
        with fc2:
            filt = st.selectbox("篩選", ["全部", "未到 ⬜", "已到 ✅"],
                                label_visibility="collapsed", key="list_filter")

        view = list(computed)
        if search:
            sq = search.lower()
            view = [s for s in view if sq in s["name"].lower() or sq in s.get("class", "").lower()]
        if filt == "未到 ⬜":
            view = [s for s in view if s["status"] == "absent"]
        elif filt == "已到 ✅":
            view = [s for s in view if s["status"] == "present"]

        abs_n  = sum(1 for s in view if s["status"] == "absent")
        pres_v = sum(1 for s in view if s["status"] == "present")
        st.markdown(f"""
<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
  <span style="background:#dbeafe;color:#1d4ed8;border-radius:999px;padding:3px 12px;font-size:.8rem;font-weight:700;">共 {len(view)} 人</span>
  <span style="background:#dcfce7;color:#166534;border-radius:999px;padding:3px 12px;font-size:.8rem;font-weight:700;">✅ 已到 {pres_v}</span>
  <span style="background:#fee2e2;color:#991b1b;border-radius:999px;padding:3px 12px;font-size:.8rem;font-weight:700;">⬜ 未到 {abs_n}</span>
</div>
""", unsafe_allow_html=True)

        for s in view:
            _student_card(s, key_prefix="L_")

# ─────────────────────────── TAB: 歷史紀錄 ────────────────────────────────────
with tab_history:
    all_dates = load_dates()
    if not all_dates:
        st.info("尚無任何歷史紀錄。")
    else:
        dc1, dc2 = st.columns([3, 1])
        with dc1:
            sel = st.selectbox("日期", all_dates, label_visibility="collapsed", key="hist_date")
        with dc2:
            exp_btn = st.button("⬇️ 匯出", use_container_width=True, key="hist_export")

        if sel:
            h_rec  = load_records(sel)
            h_data = merge(students, h_rec)

            known = {s["id"] for s in students}
            for rid, rec in h_rec.items():
                if rid not in known:
                    h_data.append({
                        "id": rid, "name": rec.get("name", "未知"),
                        "class": rec.get("class", ""), "number": rec.get("number", ""),
                        "notes": "", "activities": [],
                        "status": "present" if rec.get("status") == "present" else "absent",
                        "time": rec.get("time", ""), "dailyNote": rec.get("dailyNote", ""),
                    })
            h_data.sort(key=lambda s: (s.get("class", ""), int(s.get("number") or 0)))

            h_pres = sum(1 for s in h_data if s["status"] == "present")
            h_pct  = int(h_pres / len(h_data) * 100) if h_data else 0

            st.markdown(f"""
<div style="background:white;border-radius:12px;padding:12px 16px;margin-bottom:12px;
            border:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;">
  <span style="font-weight:700;color:#1e293b;">{sel}</span>
  <span style="color:#64748b;font-size:.88rem;">出席 <strong style="color:#16a34a">{h_pres}</strong> / {len(h_data)} 人　({h_pct}%)</span>
</div>
""", unsafe_allow_html=True)
            st.progress(h_pct / 100)

            if exp_btn:
                st.download_button(
                    "📥 下載 CSV", data=make_csv(h_data, sel),
                    file_name=f"歸程隊歷史_{sel}.csv", mime="text/csv", key="dl_hist",
                )

            st.markdown("<br>", unsafe_allow_html=True)
            for s in h_data:
                is_p = s["status"] == "present"
                op   = "1" if is_p else "0.5"
                ic   = "✅" if is_p else "❌"
                tt   = f'<span style="font-size:.75rem;color:#16a34a;margin-left:8px;">🕐 {s["time"]}</span>' if s.get("time") else ""
                nt   = f'<div style="font-size:.78rem;color:#b91c1c;margin-top:3px;">📢 {s["dailyNote"]}</div>' if s.get("dailyNote") else ""
                st.markdown(f"""
<div style="background:white;border:1px solid #e2e8f0;border-radius:10px;
            padding:8px 14px;margin-bottom:3px;opacity:{op};">
  <span style="font-weight:700;">{ic} {s['name']}</span>{tt}
  <div style="font-size:.78rem;color:#64748b;margin-top:2px;">
    <span style="background:#e2e8f0;border-radius:4px;padding:1px 6px;margin-right:4px;">{s.get('class', '')}</span>{s.get('number', '')}號
  </div>
  {nt}
</div>
""", unsafe_allow_html=True)

# ─────────────────────────── TAB: 設定 ────────────────────────────────────────
with tab_settings:
    st.markdown("### ⬇️ 匯出今日紀錄")
    if computed:
        st.download_button(
            "📥 下載今日出席名單 (CSV)", data=make_csv(computed, td),
            file_name=f"歸程隊點名_{td}.csv", mime="text/csv", use_container_width=True,
        )

    st.markdown("---")
    st.markdown("### 📋 下載現有名單")
    if students:
        buf = io.StringIO()
        buf.write("\ufeff")
        w2 = csv.writer(buf)
        w2.writerow(["班級", "學號", "姓名", "跟隨兄/姊回家", "星期一", "星期二", "星期三", "星期四", "星期五"])
        for s in students:
            acts = {a.split(": ")[0]: a.split(": ")[1] for a in (s.get("activities") or []) if ": " in a}
            w2.writerow([s.get("class", ""), s.get("number", ""), s.get("name", ""), s.get("notes", ""),
                         acts.get("星期一", ""), acts.get("星期二", ""), acts.get("星期三", ""),
                         acts.get("星期四", ""), acts.get("星期五", "")])
        st.download_button(
            "📥 下載現有雲端名單 (CSV)", data=buf.getvalue().encode("utf-8"),
            file_name="歸程隊現有名單.csv", mime="text/csv", use_container_width=True,
        )

    st.markdown("---")
    st.markdown("### ☁️ 上傳 / 更新雲端名單")
    st.caption("欄位：班級、學號、姓名、跟隨兄/姊回家、星期一～五。**QR 碼內容為學生姓名。**")
    uploaded = st.file_uploader("選擇 CSV", type=["csv"], label_visibility="collapsed")

    if uploaded:
        try:
            content = uploaded.read().decode("utf-8-sig")
            rows    = list(csv.reader(io.StringIO(content)))
            cidx    = {}
            hrow    = -1
            for i, row in enumerate(rows):
                ci = next((j for j, c in enumerate(row) if "班級" in str(c)), -1)
                ni = next((j for j, c in enumerate(row) if "姓名" in str(c)), -1)
                if ci != -1 and ni != -1:
                    hrow = i
                    cidx["class"] = ci
                    cidx["name"]  = ni
                    cidx["num"]   = next((j for j, c in enumerate(row) if "學號" in str(c)), -1)
                    cidx["notes"] = next((j for j, c in enumerate(row) if "跟隨" in str(c)), -1)
                    for day, label in [("mon", "星期一"), ("tue", "星期二"), ("wed", "星期三"),
                                       ("thu", "星期四"), ("fri", "星期五")]:
                        cidx[day] = next((j for j, c in enumerate(row) if label in str(c)), -1)
                    if cidx["mon"] == -1 and cidx.get("notes", -1) != -1:
                        base = cidx["notes"]
                        for i2, d2 in enumerate(["mon", "tue", "wed", "thu", "fri"]):
                            cidx[d2] = base + 1 + i2
                    break

            if hrow == -1:
                st.error("❌ 找不到標題列，請確認 CSV 包含「班級」和「姓名」欄位。")
            else:
                def _g(row, key, default=""):
                    idx = cidx.get(key, -1)
                    return str(row[idx]).strip() if idx != -1 and idx < len(row) and row[idx] else default

                new_list = []
                for row in rows[hrow + 1:]:
                    if not any(row):
                        continue
                    cls  = _g(row, "class")
                    name = _g(row, "name")
                    if not cls or not name or "班級" in cls or "姓名" in name:
                        continue
                    num   = _g(row, "num")
                    notes = _g(row, "notes")
                    acts  = []
                    for key2, lbl in [("mon", "星期一"), ("tue", "星期二"), ("wed", "星期三"),
                                      ("thu", "星期四"), ("fri", "星期五")]:
                        val = _g(row, key2)
                        if val and not val.isdigit() and lbl not in val:
                            acts.append(f"{lbl}: {val}")
                    new_list.append({
                        "id": f"C_{cls}_{num}_{name}", "class": cls,
                        "number": num, "name": name,
                        "notes": notes, "activities": acts,
                    })

                st.info(f"解析完成，共 **{len(new_list)}** 筆資料")
                st.dataframe(
                    pd.DataFrame([{k: v for k, v in s.items() if k != "activities"} for s in new_list]),
                    use_container_width=True, height=220,
                )
                if new_list and st.button("☁️ 確認上傳至雲端", type="primary", use_container_width=True):
                    with st.spinner("上傳中…"):
                        batch = db.batch()
                        for doc in db.collection("students").stream():
                            batch.delete(doc.reference)
                        for s in new_list:
                            batch.set(db.collection("students").document(s["id"]), s)
                        batch.commit()
                    _clear()
                    st.success(f"✅ 已上傳 {len(new_list)} 筆學生資料！")
                    st.rerun()
        except Exception as e:
            st.error(f"❌ 讀取 CSV 錯誤：{e}")

    st.markdown("---")
    st.markdown("### 🔓 登出")
    if st.button("登出系統", use_container_width=True):
        st.session_state.auth = False
        st.rerun()
