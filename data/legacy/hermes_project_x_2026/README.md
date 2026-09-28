# Legacy：Hermes Project X（repo B `fung2222/project-x-2026`）— 唯讀存檔

- **來源**：`fung2222/project-x-2026` @ `29c2615`（2026-09-28 10:48 HKT），即係 Hermes 由 2026-07-08 起每日自動 push 嘅數據，一直更新到 2026-09-28（05:00 收市報告、08:30 隔夜複盤、21:30 日報）。
- `data/`：repo B 嘅 `data/` 原樣複製（portfolio、pnl_history、reports_index、market_snapshot、daily_report、futu_positions，同 218 份每日／收市報告 md/html）。
- `export_2026-09-28/`：Hermes 喺 2026-09-28 匯出嘅 Project X pipeline 源碼、排程、規則同最近報告（**只作參考，唔會喺呢個 repo 執行**）。`mag7_observer/` 冇複製過嚟：Mag7 觀察池已由 Roy 喺 2026-09-28 退役，原檔留喺 repo B `export/2026-09-28/mag7_observer/` 做存檔。
- **Hermes 模擬倉（HKD 5,000 ≈ USD 641.03，2026-07-08 開倉）**：NVDA 0.5 / TSLA 0.5 / RKLB 1.0，現金 USD 257.70；2026-09-28 總值 USD 630.24（−1.68%）。
  - ⚠️ 止損只標 flag、從未執行：RKLB 自 2026-07-16 起低於 −10% 止損仍持有；TSLA 7–9 月最多 −24.7% 都冇平倉。所以呢本 book 嘅 P&L **唔可以**同 Project X（HKD 10k，2026-09-13 起，自動執行 SL/TP）比較或者合併計算。
  - 冇手續費、碎股、FX 固定 7.8。
- 呢度嘅數據**唔計入**主網站嘅權益曲線、命中率或者任何規則判斷；網站只喺「報告存檔」同「組合 → Legacy」摺埋顯示。
- 唔好改呢個資料夾嘅檔案（歷史紀錄）。要更新就由 repo B 重新複製並記錄 commit。
