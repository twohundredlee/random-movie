# 抽一部twohundredlee看過的電影

從 twohundredlee 在 [Letterboxd](https://letterboxd.com/twohundredlee/) 看過的電影裡隨機抽一部，顯示海報、評分、評論與電影資訊。

- `index.html`：網頁
- `films.json`：片單資料（1496 部，2026-10-29）
- `posters/`：海報拼圖

電影資料與中文譯名來源：Letterboxd、TMDB。

## 自動更新

`.github/workflows/update.yml` 每天台灣時間 04:17 執行 `scripts/update.py`：
讀 Letterboxd RSS（最近的日記），把新片、評分、評論併進 `films.json`，新片資料與海報來自 TMDB API。
需要在 Settings → Secrets and variables → Actions 新增 `TMDB_API_KEY`。
`data/seen.json` 記錄已處理過的日記，避免重複計算。
