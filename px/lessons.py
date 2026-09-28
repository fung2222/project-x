"""今日學一樣: one short, practical lesson per daily report. Curated list (no LLM); no repeat within 30 days.
History: state/lesson_history.json {"YYYY-MM-DD": index}. Same day -> same lesson (re-runs are consistent)."""
import datetime as dt
import json
import os
import tempfile

from .config import STATE_DIR

LESSONS = [
    "止蝕係入場之前就要諗好嘅價，唔係跌咗先諗。落單前問自己：跌到幾多我一定走？",
    "每注最多輸本金 2%：US$1,280 本金即係每注最多蝕大約 US$26。咁樣連輸 5 次都仲有九成本金。",
    "唔好攤平：越跌越買會令一隻錯嘅股票食晒你啲錢。跌穿止蝕就走，錢留返畀下一個機會。",
    "賺錢嘅股票唔好一升就賣、蝕錢嘅唔好死抱。好多人調轉咗做，所以長遠輸錢。",
    "業績公布前後股價可以一日跳 20%。業績前 5 個交易日唔開新倉，就係避開呢種賭博。",
    "現金都係一個倉位。冇好機會嘅日子唔買嘢，本身就係一個正確決定。",
    "手續費會食利潤：富途每張單大約 US$2，一買一賣 US$4。買 US$100 嘅股票要升 4% 先打和。",
    "睇大市先：納指大跌嘅日子，九成股票都會跌。個股好唔好，要同大市比較先知。",
    "恐慌指數（VIX）超過 30 代表市場好驚，波幅會好大。呢啲日子少做少錯。",
    "一隻股票升咗好多唔代表會繼續升，亦唔代表一定跌。我哋只跟預先定好嘅規則做。",
    "分散：同一個主題（例如全部都係量子股）唔好買多過一隻，一單壞消息會同時打沉晒。",
    "止賺價都要預先定好。到咗目標可以先賣，唔好因為貪心而由賺變蝕。",
    "賣咗之後再升好正常，唔好 FOMO 即刻追返。等下一個有計劃嘅機會。",
    "新聞標題好誇張唔代表影響好大。先睇股價同大市比較，再決定係咪要理。",
    "小型股波幅大：一日升跌 5–10% 好常見，所以注碼要細、止蝕要守。",
    "記錄每一單：買入原因、止蝕、止賺、結果。20–30 單之後先知自己個方法得唔得。",
    "唔好用借返嚟嘅錢或者生活費買股票。輸得起嘅錢先放入市場。",
    "「平」唔等於「抵」：US$3 嘅股票可以再跌 50%，股價低唔係買入理由。",
    "成交量大先容易買賣。成交少嘅股票，想走嗰陣可能要賣得好蝕。",
    "股價企喺 50 日平均價之上，通常代表中期趨勢向上；跌穿就要小心。",
    "唔好因為一日大跌就改止蝕。止蝕一改再改，最後就會變成蝕大錢。",
    "開市頭半個鐘波動最大，唔使急。等價格穩定啲先決定。",
    "美股時間：夏令時間香港晚上 9:30 開市，冬令時間 10:30 開市，凌晨 4 點／5 點收市。",
    "港幣同美元掛鈎（約 7.8），所以美股嘅盈虧主要來自股價，唔係匯率。",
    "連續輸幾單好正常，唔好因為想「追返」而加大注碼。守住每注 2% 風險。",
    "唔好聽「保證升」嘅貼士。冇人可以保證，我哋只講情境同機會率。",
    "紙上倉係對照組：同真倉比較，睇下系統規則同你自己決定邊個做得好啲。",
    "買之前講得出三樣嘢：點解買、幾時走（止蝕）、目標幾多（止賺）。講唔出就唔好買。",
    "大市急跌嘅日子，先檢查持倉距離止蝕有幾遠，唔好急住撈底。",
    "盤前盤後價格可以同正式開市差好遠，系統只用正式交易時段嘅價做決定。",
    "「回報／風險」至少 2 倍先值得做：可能蝕 US$10，目標最少要賺 US$20。",
    "高位追入最易蝕：離 20 日平均價太遠嘅股票，等回落先考慮。",
    "有持倉嘅公司出新聞，先睇係咪影響佢盈利（業績、合約、集資），再決定。",
    "集資（增發新股）通常會令股價短期受壓，因為股份數目變多咗。",
    "分析師調高／調低評級，通常只影響一兩日，唔好單憑呢個買賣。",
    "複利要時間：每年穩定賺 10–15% 已經好好，唔好追求一個月翻倍。",
    "休息都係交易嘅一部分：心情差、好攰嘅時候唔好落單。",
    "一隻股票冇起色超過一個月，可以考慮換去更強嘅機會（時間止蝕）。",
    "唔好睇住個價格跳動做決定。系統每 5 分鐘幫你睇真倉，有事先通知你。",
    "檢討要睇過程唔係結果：守規則但蝕錢係好交易；唔守規則但賺錢係壞習慣。",
]


def _path():
    return os.path.join(STATE_DIR, "lesson_history.json")


def _load():
    try:
        with open(_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def pick(day=None, save=True, no_repeat_days=30):
    day = day or dt.date.today()
    hist = _load()
    k = day.isoformat()
    if k in hist and 0 <= int(hist[k]) < len(LESSONS):
        return LESSONS[int(hist[k])]
    cutoff = (day - dt.timedelta(days=no_repeat_days)).isoformat()
    recent = {int(v) for d, v in hist.items() if cutoff <= d < k}
    n = len(LESSONS)
    start = day.toordinal() % n
    idx = next((i % n for i in range(start, start + n) if i % n not in recent), start)
    if save:
        hist[k] = idx
        hist = {d: v for d, v in hist.items() if d >= (day - dt.timedelta(days=90)).isoformat()}
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".lessons.", dir=STATE_DIR)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(hist, f)
            os.replace(tmp, _path())
        except Exception as e:
            print("[lessons] history write failed:", type(e).__name__)
    return LESSONS[idx]
