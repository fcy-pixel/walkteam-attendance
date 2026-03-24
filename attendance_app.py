"""
歸程隊C隊點名系統 - Streamlit 版
QR 碼內容為學生姓名，以姓名比對完成點名
"""

import base64
import io
import json
import csv

import cv2
import numpy as np
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from PIL import Image
import streamlit as st
from datetime import datetime

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="歸程隊C隊點名系統",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  [data-testid="stSidebar"] { display: none; }
  .block-container { padding-top: 1rem; padding-bottom: 1rem; }
  .stTabs [data-baseweb="tab"] { font-size: 1rem; font-weight: 600; }
  div[data-testid="stMetricValue"] { font-size: 2rem; }
</style>
""", unsafe_allow_html=True)

# ── Password Gate ─────────────────────────────────────────────────────────────
_PASSWORD = "ktps"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("## 🔒 歸程隊C隊點名系統")
        st.markdown("---")
        pwd = st.text_input("請輸入密碼", type="password", key="login_pwd")
        if st.button("登入", use_container_width=True, type="primary"):
            if pwd == _PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤，請重試")
    st.stop()

# ── Firebase Init ─────────────────────────────────────────────────────────────
@st.cache_resource
def _init_firebase():
    if not firebase_admin._apps:
        try:
            # Accepts base64-encoded JSON (FIREBASE_JSON_B64)
            # or a TOML table ([FIREBASE_SERVICE_ACCOUNT])
            if "FIREBASE_JSON_B64" in st.secrets:
                cred_dict = json.loads(base64.b64decode(st.secrets["FIREBASE_JSON_B64"]).decode())
            elif "FIREBASE_SERVICE_ACCOUNT" in st.secrets:
                raw = st.secrets["FIREBASE_SERVICE_ACCOUNT"]
                cred_dict = json.loads(raw) if isinstance(raw, str) else dict(raw)
            else:
                return None, "找不到 FIREBASE_JSON_B64 或 FIREBASE_SERVICE_ACCOUNT secret"
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            return None, str(e)
    return firestore.client(), None

_db, _db_error = _init_firebase()

if _db is None:
    st.error(f"❌ Firebase 連線失敗：{_db_error}")
    st.info("""
請在 Streamlit Cloud → App settings → Secrets 中加入以下設定：

```toml
FIREBASE_JSON_B64 = "eyJ0eXBlIjo..."
```

**取得方式（在你的 Mac 終端機執行）：**
```bash
python3 /tmp/make_b64_secret.py
```
然後將剪貼簿內容貼到 Secrets 即可。
    """)
    st.stop()

db = _db

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


@st.cache_data(ttl=8)
def load_students() -> list[dict]:
    docs = db.collection("students").stream()
    students = [doc.to_dict() for doc in docs]
    return sorted(students, key=lambda s: (s.get("class", ""), int(s.get("number") or 0)))


@st.cache_data(ttl=5)
def load_records(date_str: str) -> dict:
    snap = db.collection("daily_records").document(date_str).get()
    return snap.to_dict().get("records", {}) if snap.exists else {}


@st.cache_data(ttl=30)
def load_all_dates() -> list[str]:
    docs = db.collection("daily_records").stream()
    return sorted([doc.id for doc in docs], reverse=True)


def _invalidate():
    load_students.clear()
    load_records.clear()
    load_all_dates.clear()


def _set_status(student: dict, new_status: str):
    today = get_today_str()
    now = datetime.now()
    time_str = now.strftime("%H:%M") if new_status == "present" else None
    db.collection("daily_records").document(today).set({
        "date": today,
        "timestamp": now.timestamp(),
        "records": {
            student["id"]: {
                "status": new_status,
                "time": time_str,
                "name": student["name"],
                "class": student.get("class", ""),
                "number": student.get("number", ""),
            }
        }
    }, merge=True)
    _invalidate()


def _set_note(student: dict, note: str):
    today = get_today_str()
    now = datetime.now()
    db.collection("daily_records").document(today).set({
        "date": today,
        "timestamp": now.timestamp(),
        "records": {
            student["id"]: {
                "dailyNote": note,
                "name": student["name"],
                "class": student.get("class", ""),
                "number": student.get("number", ""),
            }
        }
    }, merge=True)
    _invalidate()


def _merge(students: list[dict], records: dict) -> list[dict]:
    result = []
    for s in students:
        rec = records.get(s["id"], {})
        result.append({
            **s,
            "status": "present" if rec.get("status") == "present" else "absent",
            "time": rec.get("time", ""),
            "dailyNote": rec.get("dailyNote", ""),
        })
    return result


def _decode_qr(image_bytes: bytes) -> str | None:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img)
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(arr)
    return data.strip() if data else None


def _generate_csv(data: list[dict], date_str: str) -> bytes:
    buf = io.StringIO()
    buf.write(f"日期：{date_str}\n")
    writer = csv.writer(buf)
    writer.writerow(["班級", "學號", "姓名", "狀態", "報到時間", "今日通報", "備註(跟隨)", "活動"])
    for s in data:
        acts = "、".join(s.get("activities") or [])
        writer.writerow([
            s.get("class", ""), s.get("number", ""), s.get("name", ""),
            "已到" if s.get("status") == "present" else "未到",
            s.get("time", ""), s.get("dailyNote", ""),
            s.get("notes", ""), acts,
        ])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


# ── Header ────────────────────────────────────────────────────────────────────
today_str = get_today_str()
today_label = datetime.now().strftime("%Y年%m月%d日")

students_all = load_students()
records_today = load_records(today_str)
computed_all = _merge(students_all, records_today)
present_count = sum(1 for s in computed_all if s["status"] == "present")
total_count = len(computed_all)

st.markdown(f"""
<div style="background:linear-gradient(135deg,#2563eb,#1e40af);
            padding:14px 22px;border-radius:12px;color:white;margin-bottom:12px;
            display:flex;justify-content:space-between;align-items:center;">
  <div>
    <div style="font-size:1.3rem;font-weight:700;">🏃 歸程隊C隊點名系統</div>
    <div style="opacity:.85;font-size:.88rem;margin-top:3px;">{today_label}</div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:2rem;font-weight:700;line-height:1;">{present_count}/{total_count}</div>
    <div style="font-size:.75rem;opacity:.8;">今日已出席</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_list, tab_scan, tab_history, tab_settings = st.tabs(
    ["📋 今日名單", "📷 掃描 / 搜尋", "📅 歷史紀錄", "⚙️ 設定"]
)

# ═══════════════════════════════════════════════════════════
# Tab 1 — 今日名單
# ═══════════════════════════════════════════════════════════
with tab_list:
    c_search, c_filter, c_refresh = st.columns([4, 2, 1])
    with c_search:
        search = st.text_input("搜尋", placeholder="搜尋班級或姓名…",
                               label_visibility="collapsed", key="list_search")
    with c_filter:
        filt = st.selectbox("篩選", ["全部", "未到 ⬜", "已到 ✅"],
                            label_visibility="collapsed", key="list_filter")
    with c_refresh:
        if st.button("🔄", help="重新整理", use_container_width=True):
            _invalidate(); st.rerun()

    if not students_all:
        st.info("🗂️ 雲端尚無學生資料，請前往「設定」上傳 CSV 名單。")
        st.stop()

    # Apply filter
    view = list(computed_all)
    if search:
        sq = search.lower()
        view = [s for s in view if sq in s.get("name", "").lower()
                or sq in s.get("class", "").lower()]
    if filt == "未到 ⬜":
        view = [s for s in view if s["status"] == "absent"]
    elif filt == "已到 ✅":
        view = [s for s in view if s["status"] == "present"]

    st.markdown(f"**顯示 {len(view)} 筆**（共 {total_count} 人，已到 {present_count} 人）")
    st.markdown("---")

    for s in view:
        is_present = s["status"] == "present"
        bg = "#f0fdf4" if is_present else "#fafafa"
        border = "#22c55e" if is_present else "#d1d5db"
        time_txt = f"&nbsp;&nbsp;<small style='color:#16a34a'>🕐 {s['time']}</small>" if s['time'] else ""
        note_indicator = " 📢" if s.get("dailyNote") else ""

        st.markdown(f"""
<div style="background:{bg};border:1px solid {border};border-left:4px solid {border};
            border-radius:10px;padding:10px 14px;margin-bottom:6px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:6px;">
    <div style="flex:1;min-width:200px;">
      <span style="font-size:1.1rem;font-weight:700;">{'✅' if is_present else '⬜'} {s['name']}{note_indicator}</span>{time_txt}
      <br><span style="background:#e5e7eb;border-radius:4px;padding:1px 7px;font-size:.8rem;margin-right:4px;">{s.get('class','')}</span>
      <span style="font-size:.85rem;color:#6b7280;">{s.get('number','')}號</span>
      {'<br><span style="font-size:.8rem;color:#3b82f6;">👨‍👧 '+s['notes']+'</span>' if s.get('notes') else ''}
      {''.join(f'<br><span style="font-size:.8rem;color:#7c3aed;">🏃 '+a+'</span>' for a in (s.get('activities') or []))}
      {'<br><div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:4px 8px;margin-top:4px;font-size:.85rem;color:#b91c1c;">📢 今日通報：'+s['dailyNote']+'</div>' if s.get('dailyNote') else ''}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

        col_note, col_btn = st.columns([1, 1])
        with col_note:
            edit_key = f"edit_note_{s['id']}"
            note_label = "✏️ 編輯通報" if s.get("dailyNote") else "📝 新增通報"
            if st.button(note_label, key=f"note_open_{s['id']}", use_container_width=True):
                st.session_state[edit_key] = not st.session_state.get(edit_key, False)
        with col_btn:
            btn_label = "↩️ 取消報到" if is_present else "✅ 報到"
            if st.button(btn_label, key=f"att_{s['id']}", use_container_width=True,
                         type="secondary" if is_present else "primary"):
                _set_status(s, "absent" if is_present else "present")
                st.rerun()

        # Inline note editor
        if st.session_state.get(f"edit_note_{s['id']}"):
            with st.form(key=f"form_note_{s['id']}"):
                st.caption(f"正在編輯：{s.get('class','')} {s['name']}")
                note_val = st.text_area("今日通報備註", value=s.get("dailyNote", ""),
                                        placeholder="例如：家長接回、早退、病假/事假、自行放學…",
                                        height=80)
                q_cols = st.columns(4)
                quick_notes = ["家長接回", "早退", "病假 / 事假", "自行放學"]
                # quick-fill buttons are cosmetic only; user types in text_area
                st.caption("💡 快速輸入（複製後貼上）：" + "  |  ".join([f"`{q}`" for q in quick_notes]))
                s_col, c_col = st.columns(2)
                if s_col.form_submit_button("💾 儲存並通報", type="primary", use_container_width=True):
                    _set_note(s, note_val.strip())
                    st.session_state[f"edit_note_{s['id']}"] = False
                    st.success(f"✅ 已發佈 {s['name']} 的今日通報")
                    st.rerun()
                if c_col.form_submit_button("取消", use_container_width=True):
                    st.session_state[f"edit_note_{s['id']}"] = False
                    st.rerun()

        st.divider()

# ═══════════════════════════════════════════════════════════
# Tab 2 — 掃描 / 搜尋
# ═══════════════════════════════════════════════════════════
with tab_scan:
    st.markdown("#### 🔍 手動搜尋點名")
    m_col, btn_col = st.columns([4, 1])
    with m_col:
        manual = st.text_input("輸入學號、姓名或班級", placeholder="輸入後按 Enter 或點擊搜尋…",
                               key="manual_input", label_visibility="collapsed")
    with btn_col:
        manual_btn = st.button("搜尋", key="manual_search_btn", use_container_width=True, type="primary")

    if manual_btn or (manual and st.session_state.get("_manual_prev") != manual):
        st.session_state["_manual_prev"] = manual
        if manual.strip():
            q = manual.strip().lower()
            match = next((s for s in computed_all
                          if s["name"].lower() == q
                          or (s.get("class", "") + str(s.get("number", ""))).lower() == q
                          or str(s.get("number", "")) == q), None)
            if match:
                new_status = "absent" if match["status"] == "present" else "present"
                _set_status(match, new_status)
                msg = f"✅ 已報到：{match['name']}" if new_status == "present" else f"↩️ 已取消報到：{match['name']}"
                st.success(msg)
                st.rerun()
            else:
                st.error(f"❌ 找不到符合的學生：「{manual.strip()}」")

    st.markdown("---")
    st.markdown("#### 📷 QR 碼掃描點名")
    st.caption("QR 碼內容為學生姓名。拍下 QR 碼後系統自動識別並完成點名。")

    cam_img = st.camera_input("對準學生 QR 碼後按下拍照", label_visibility="visible", key="qr_camera")

    if cam_img is not None:
        decoded = _decode_qr(cam_img.getvalue())
        if decoded:
            # Match by name or student ID
            match = next((s for s in computed_all
                          if s["name"] == decoded or s["id"] == decoded), None)
            if match:
                if match["status"] == "present":
                    st.info(f"ℹ️ {match['name']} 已經報到過了（{match['time']}）")
                else:
                    _set_status(match, "present")
                    st.success(f"✅ 已報到：{match['name']} （{match.get('class','')} {match.get('number','')}號）")
                    if match.get("dailyNote"):
                        st.warning(f"📢 今日通報：{match['dailyNote']}")
                    st.rerun()
            else:
                st.error(f"❌ 找不到學生：「{decoded}」")
        else:
            st.warning("⚠️ 未能識別 QR 碼，請確保 QR 碼清晰且完整在畫面中。")

    st.markdown("---")
    st.markdown("#### 📊 最近出席記錄")
    recent = [s for s in computed_all if s["status"] == "present" and s.get("time")]
    recent_sorted = sorted(recent, key=lambda s: s.get("time", ""), reverse=True)[:10]
    if recent_sorted:
        for s in recent_sorted:
            st.markdown(f"✅ **{s['name']}** `{s.get('class','')}` {s.get('number','')}號 — 🕐 {s['time']}")
    else:
        st.caption("暫無出席記錄")

# ═══════════════════════════════════════════════════════════
# Tab 3 — 歷史紀錄
# ═══════════════════════════════════════════════════════════
with tab_history:
    all_dates = load_all_dates()

    if not all_dates:
        st.info("尚無任何歷史紀錄。")
    else:
        h_col1, h_col2 = st.columns([3, 1])
        with h_col1:
            selected_date = st.selectbox("選擇日期", all_dates, key="hist_date")
        with h_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            export_hist = st.button("⬇️ 匯出 CSV", use_container_width=True, key="export_hist")

        if selected_date:
            hist_records = load_records(selected_date)
            hist_data = _merge(students_all, hist_records)

            # Include orphan records (students no longer in base list)
            known_ids = {s["id"] for s in students_all}
            for rid, rec in hist_records.items():
                if rid not in known_ids:
                    hist_data.append({
                        "id": rid, "name": rec.get("name", "未知"),
                        "class": rec.get("class", ""), "number": rec.get("number", ""),
                        "notes": "", "activities": [],
                        "status": "present" if rec.get("status") == "present" else "absent",
                        "time": rec.get("time", ""), "dailyNote": rec.get("dailyNote", ""),
                    })

            hist_data.sort(key=lambda s: (s.get("class", ""), int(s.get("number") or 0)))
            h_present = sum(1 for s in hist_data if s["status"] == "present")
            st.markdown(f"**{selected_date}　出席：{h_present} / {len(hist_data)}**")
            st.progress(h_present / max(len(hist_data), 1))

            if export_hist:
                csv_bytes = _generate_csv(hist_data, selected_date)
                st.download_button(
                    "📥 下載歷史記錄 CSV",
                    data=csv_bytes,
                    file_name=f"歸程隊歷史紀錄_{selected_date}.csv",
                    mime="text/csv",
                    key="dl_hist_csv",
                )

            st.markdown("---")
            for s in hist_data:
                is_present = s["status"] == "present"
                icon = "✅" if is_present else "❌"
                time_txt = f"&nbsp;🕐 {s['time']}" if s["time"] else ""
                note_txt = f"<br><span style='color:#b91c1c;font-size:.85rem;'>📢 通報：{s['dailyNote']}</span>" if s.get("dailyNote") else ""
                opacity = "1" if is_present else "0.55"
                st.markdown(f"""
<div style="padding:8px 12px;border-radius:8px;border:1px solid #e5e7eb;margin-bottom:5px;opacity:{opacity}">
  {icon} <strong>{s['name']}</strong>
  <span style="background:#e5e7eb;border-radius:4px;padding:1px 6px;font-size:.78rem;margin-left:6px;">{s.get('class','')}</span>
  <span style="font-size:.82rem;color:#6b7280;">{s.get('number','')}號</span>
  <span style="font-size:.82rem;">{time_txt}</span>
  {note_txt}
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# Tab 4 — 設定
# ═══════════════════════════════════════════════════════════
with tab_settings:
    # Export today
    st.markdown("### ⬇️ 匯出今日紀錄")
    if computed_all:
        csv_today = _generate_csv(computed_all, today_str)
        st.download_button(
            "📥 下載今日出席名單 (CSV)",
            data=csv_today,
            file_name=f"歸程隊點名紀錄_{today_str}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("今日尚無資料")

    st.markdown("---")

    # Download existing roster
    st.markdown("### 📋 下載現有名單")
    if students_all:
        buf = io.StringIO()
        buf.write("\ufeff")
        writer = csv.writer(buf)
        writer.writerow(["班級", "學號", "姓名", "跟隨兄/姊回家", "星期一", "星期二", "星期三", "星期四", "星期五"])
        for s in students_all:
            acts = {a.split(": ")[0]: a.split(": ")[1] for a in (s.get("activities") or []) if ": " in a}
            writer.writerow([
                s.get("class", ""), s.get("number", ""), s.get("name", ""),
                s.get("notes", ""),
                acts.get("星期一", ""), acts.get("星期二", ""), acts.get("星期三", ""),
                acts.get("星期四", ""), acts.get("星期五", ""),
            ])
        st.download_button(
            "📥 下載現有雲端名單 (CSV)",
            data=buf.getvalue().encode("utf-8"),
            file_name="歸程隊現有名單.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("雲端尚無名單資料")

    st.markdown("---")

    # Upload CSV
    st.markdown("### ☁️ 上傳 / 更新雲端名單")
    st.caption("CSV 欄位：班級、學號、姓名、跟隨兄/姊回家、星期一、星期二、星期三、星期四、星期五。**QR 碼內容為學生姓名。**")

    uploaded = st.file_uploader("選擇 CSV 檔案", type=["csv"], key="csv_upload")

    if uploaded:
        try:
            content = uploaded.read().decode("utf-8-sig")
            reader = csv.reader(io.StringIO(content))
            rows = list(reader)

            col_idx = {}
            header_row = -1
            for i, row in enumerate(rows):
                class_col = next((j for j, c in enumerate(row) if "班級" in str(c)), -1)
                name_col = next((j for j, c in enumerate(row) if "姓名" in str(c)), -1)
                if class_col != -1 and name_col != -1:
                    header_row = i
                    col_idx["class"] = class_col
                    col_idx["name"] = name_col
                    col_idx["num"] = next((j for j, c in enumerate(row) if "學號" in str(c)), -1)
                    col_idx["notes"] = next((j for j, c in enumerate(row) if "跟隨" in str(c)), -1)
                    col_idx["mon"] = next((j for j, c in enumerate(row) if "星期一" in str(c)), -1)
                    col_idx["tue"] = next((j for j, c in enumerate(row) if "星期二" in str(c)), -1)
                    col_idx["wed"] = next((j for j, c in enumerate(row) if "星期三" in str(c)), -1)
                    col_idx["thu"] = next((j for j, c in enumerate(row) if "星期四" in str(c)), -1)
                    col_idx["fri"] = next((j for j, c in enumerate(row) if "星期五" in str(c)), -1)
                    # Fallback: days right after notes column
                    if col_idx["mon"] == -1 and col_idx["notes"] != -1:
                        n = col_idx["notes"]
                        col_idx["mon"], col_idx["tue"], col_idx["wed"] = n+1, n+2, n+3
                        col_idx["thu"], col_idx["fri"] = n+4, n+5
                    break

            if header_row == -1:
                st.error("❌ 找不到標題列，請確認 CSV 包含「班級」和「姓名」欄位。")
            else:
                new_list = []

                def _get(row, key, default=""):
                    idx = col_idx.get(key, -1)
                    return str(row[idx]).strip() if idx != -1 and idx < len(row) and row[idx] else default

                day_map = [("mon", "星期一"), ("tue", "星期二"), ("wed", "星期三"),
                           ("thu", "星期四"), ("fri", "星期五")]

                for row in rows[header_row + 1:]:
                    if not any(row):
                        continue
                    cls = _get(row, "class")
                    name = _get(row, "name")
                    if not cls or not name:
                        continue
                    if "班級" in cls or "姓名" in name:
                        continue
                    num = _get(row, "num")
                    notes = _get(row, "notes")
                    acts = []
                    for key, label in day_map:
                        val = _get(row, key)
                        if val and not val.isdigit() and label not in val:
                            acts.append(f"{label}: {val}")
                    new_list.append({
                        "id": f"C_{cls}_{num}_{name}",
                        "class": cls, "number": num, "name": name,
                        "notes": notes, "activities": acts,
                    })

                st.info(f"📋 解析完成，共 {len(new_list)} 筆資料")
                st.dataframe(
                    pd.DataFrame([{k: v for k, v in s.items() if k != "activities"} for s in new_list]),
                    use_container_width=True, height=250,
                )

                if new_list:
                    if st.button("☁️ 確認上傳至雲端", type="primary", use_container_width=True, key="confirm_upload"):
                        with st.spinner("上傳中…"):
                            batch = db.batch()
                            existing = db.collection("students").stream()
                            for doc in existing:
                                batch.delete(doc.reference)
                            for s in new_list:
                                ref = db.collection("students").document(s["id"])
                                batch.set(ref, s)
                            batch.commit()
                        _invalidate()
                        st.success(f"✅ 已成功上傳 {len(new_list)} 筆學生資料！")
                        st.rerun()
        except Exception as e:
            st.error(f"❌ 讀取 CSV 發生錯誤：{e}")

    st.markdown("---")
    st.markdown("### 🔓 登出")
    if st.button("登出系統", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()
