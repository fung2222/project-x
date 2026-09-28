"""
VIX Guardrail 機制 — Project X
根據市場波動情況自動調整風險參數
"""
import json, os, sys, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "portfolio.json")
sys.path.insert(0, BASE_DIR)
from px import config as _pxconfig  # thresholds: config/settings.json (single source of truth)

REGIME_DESCRIPTIONS = {
    "NORMAL": {
        "emoji": "🟢",
        "title": "正常市場",
        "color": "#27AE60",
        "description": "VIX 低於 20，波動性低，風險偏好高。適合積極操作，可以建立最多 3 個持倉，信心度門檻 75%。",
        "action": "正常操作，可以考慮買入信號",
        "max_positions": 3,
        "min_confidence": 0.75
    },
    "CAUTION": {
        "emoji": "🟡",
        "title": "謹慎市場",
        "color": "#F39C12",
        "description": "VIX 處於 20-30，市場波動中等。建議收窄持倉，提高信心度要求。",
        "action": "謹慎操作，優先高信心度信號（≥80%），減少持倉至 2 個",
        "max_positions": 2,
        "min_confidence": 0.80
    },
    "DEFENSIVE": {
        "emoji": "🔴",
        "title": "防禦市場",
        "color": "#E74C3C",
        "description": "VIX 高於 30，市場高度恐慌。建議極少操作，保持現金，等待機會。",
        "action": "防禦模式，最多 1 個持倉，信心度門檻 85%，優先觀望",
        "max_positions": 1,
        "min_confidence": 0.85
    }
}

def load_portfolio():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

def check_guardrail(vix_value=None, regime=None):
    """檢查 VIX Guardrail，返回調整後的風險參數"""
    regs = _pxconfig.load_settings()["regimes"]
    floor = _pxconfig.load_settings()["rules"]["min_confidence"]
    if regime is None:
        if vix_value is None:
            regime = "NORMAL"
        elif vix_value < regs["NORMAL"]["vix_max"]:
            regime = "NORMAL"
        elif vix_value < regs["CAUTION"]["vix_max"]:
            regime = "CAUTION"
        else:
            regime = "DEFENSIVE"

    guardrails = {k: {"max_positions": v["max_positions"], "min_confidence": max(floor, v["min_confidence"])}
                  for k, v in regs.items()}
    settings = guardrails[regime]
    desc = REGIME_DESCRIPTIONS[regime]

    return {
        "regime": regime,
        "vix_value": vix_value,
        "emoji": desc["emoji"],
        "title": desc["title"],
        "color": desc["color"],
        "description": desc["description"],
        "action": desc["action"],
        "max_positions": settings["max_positions"],
        "min_confidence": settings["min_confidence"],
        "original_rules": {
            "max_positions": guardrails["NORMAL"]["max_positions"],
            "min_confidence": guardrails["NORMAL"]["min_confidence"]
        },
        "adjusted_rules": {
            "max_positions": settings["max_positions"],
            "min_confidence": settings["min_confidence"]
        },
        "timestamp": datetime.datetime.now().isoformat()
    }

def format_guardrail_report(gr):
    """格式化為易讀的報告文本"""
    adj = gr["adjusted_rules"]
    orig = gr["original_rules"]
    vix_str = f"{gr['vix_value']:.1f}" if gr['vix_value'] else "N/A"

    report = f"""
{gr['emoji']} VIX Guardrail 狀態報告
━━━━━━━━━━━━━━━━━━━━
VIX 指數：{vix_str}
市場狀態：{gr['title']}

📊 風險參數調整：
   持倉上限：{orig['max_positions']} → {adj['max_positions']} 隻
   信心度要求：{orig['min_confidence']*100:.0f}% → {adj['min_confidence']*100:.0f}%

💡 市場描述：
{gr['description']}

🎯 建議操作：
{gr['action']}

⚠️ 重要：以上為系統自動判斷，僅供參考，不構成投資建議。
"""
    return report.strip()

if __name__ == "__main__":
    # 測試所有狀態
    for regime in ["NORMAL", "CAUTION", "DEFENSIVE"]:
        vix_vals = {"NORMAL": 17.5, "CAUTION": 24.0, "DEFENSIVE": 33.0}
        gr = check_guardrail(vix_value=vix_vals[regime], regime=regime)
        print(format_guardrail_report(gr))
        print()
