# 歸程隊C隊點名系統

以學生姓名 QR 碼為基礎的即時點名系統，使用 Firebase Firestore 作雲端資料庫。

## 功能

- 🔒 密碼登入保護
- 📋 今日名單，支援搜尋 / 篩選
- 📷 相機掃描學生姓名 QR 碼自動點名
- 🔍 手動輸入姓名 / 學號搜尋點名
- 📢 今日通報備註（家長接回、早退等）
- 📅 歷史紀錄查閱及 CSV 匯出
- ☁️ 上傳 / 下載雲端學生名單

## 部署到 Streamlit Cloud

1. Fork 或 clone 此 repo
2. 前往 [share.streamlit.io](https://share.streamlit.io)，選擇此 repo，主程式設為 `attendance_app.py`
3. 在 **App Settings → Secrets** 填入 Firebase Service Account：

```toml
FIREBASE_SERVICE_ACCOUNT = '{ ...整個 JSON 內容... }'
```

## CSV 格式

上傳名單 CSV 欄位：`班級, 學號, 姓名, 跟隨兄/姊回家, 星期一, 星期二, 星期三, 星期四, 星期五`

QR 碼內容為**學生姓名**。
