# -*- coding: utf-8 -*-
"""
v16 全艇スコア解析アプリ（完全独立版・uchisankakuベース）
=======================================================
このファイル 1 本で動作します。

データソース:
  - 開催場一覧:     uchisankaku.sakura.ne.jp/raceindex.php
  - 選手データ:     uchisankaku.sakura.ne.jp/racelist.php (全艇の進入コース6ヶ月ST等)
  - 発走時刻:       boatrace.jp (uchisankakuに全R時刻の情報が無いため)
  - レース結果/払戻: boatrace.jp/owpc/pc/race/raceresult

スコアリング:
  score_P5 のロジックを全艇に適用。
  各艇の進入コース（= 艇番）の6ヶ月平均STで評価。

買い目:
  3連単 4点 = 1位 - [2位, 3位] - [2位, 3位, 4位]

必要ライブラリ (requirements.txt):
  streamlit
  requests
  beautifulsoup4
  pandas

起動:
  streamlit run v16_all_boats_app.py
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


# ============================================================
# Racer / score_P5 （旧 v16_itigo_filter.py からインライン化）
# ============================================================
@dataclass
class Racer:
    name: str = ""
    cls: str = ""
    win_rate: Optional[float] = None
    avg_st: Optional[float] = None
    settle_st: Optional[float] = None
    settle_2rate: Optional[float] = None
    motor_2rate: Optional[float] = None
    f_count: int = 0
    exhibit_rank: Optional[int] = None
    course5_avg_st: Optional[float] = None  # 「その艇の進入コース6ヶ月ST」を格納
    weight: Optional[float] = None
    makuri_rate: Optional[float] = None


VENUE_BONUS_P5 = {"戸田": 0.5, "江戸川": 0.5, "平和島": 0.5}


def _band(value: Optional[float],
          bands: List[Tuple[float, float, float]],
          default: float = 0.0) -> float:
    if value is None:
        return default
    for lo, hi, pts in bands:
        if lo <= value < hi:
            return pts
    return default


def score_P5(b5: Racer, venue: str) -> float:
    """5号艇用スコアを全艇に流用。course5_avg_st に進入コースSTを入れる設計。"""
    s = 0.0
    s += {"A1": 2.5, "A2": 1.5, "B1": 0.0, "B2": -1.5}.get(b5.cls, 0.0)
    s += _band(b5.win_rate, [
        (6.50, 99.0, 1.5),
        (5.50, 6.50, 1.0),
        (5.00, 5.50, 0.5),
    ])
    target_st = b5.course5_avg_st if b5.course5_avg_st is not None else b5.avg_st
    attenuate = 1.0 if b5.course5_avg_st is not None else 0.5
    s += attenuate * _band(target_st, [
        (0.00, 0.16, 1.5),
        (0.16, 0.18, 0.8),
        (0.20, 9.99, -1.0),
    ])
    s += _band(b5.settle_2rate, [
        (0.50, 1.01, 1.5),
        (0.30, 0.50, 0.5),
        (0.00, 0.20, -1.0),
    ])
    if (b5.settle_st is not None and b5.avg_st is not None
            and b5.settle_st - b5.avg_st <= -0.02):
        s += 1.0
    s += _band(b5.motor_2rate, [
        (0.45, 1.01, 1.5),
        (0.30, 0.45, 0.5),
        (0.00, 0.25, -1.0),
    ])
    if b5.exhibit_rank == 1:
        s += 1.5
    elif b5.exhibit_rank == 2:
        s += 0.8
    elif b5.exhibit_rank == 6:
        s -= 1.0
    if b5.weight is not None:
        if b5.weight <= 52.0:
            s += 0.5
        elif b5.weight >= 57.0:
            s -= 0.5
    s += VENUE_BONUS_P5.get(venue, 0.0)
    return round(s, 2)


# ============================================================
# 定数
# ============================================================
st.set_page_config(page_title="v16 全艇スコア解析", layout="centered")
st.title("🚤 v16 全艇スコア解析")
st.caption("進入コース別6ヶ月データで全艇評価 (uchisankaku主体)")

UCHI_BASE = "https://uchisankaku.sakura.ne.jp"
BOAT_BASE = "https://www.boatrace.jp/owpc/pc/race"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
    )
}

JCD_TO_NAME = {
    1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川", 6: "浜名湖",
    7: "蒲郡", 8: "常滑", 9: "津", 10: "三国", 11: "びわこ", 12: "住之江",
    13: "尼崎", 14: "鳴門", 15: "丸亀", 16: "児島", 17: "宮島", 18: "徳山",
    19: "下関", 20: "若松", 21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村",
}
NAME_TO_JCD = {v: k for k, v in JCD_TO_NAME.items()}


# ============================================================
# HTTP
# ============================================================
def _fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.encoding = r.apparent_encoding or "utf-8"
        if r.status_code != 200:
            return None
        return r.text
    except Exception:
        return None


def _fnum(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    m = re.search(r"-?\d+\.\d+|-?\d+", s)
    return float(m.group()) if m else None


# ============================================================
# 開催場一覧 (uchisankaku の raceindex.php)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_day_venues(target_date: datetime.date) -> List[Tuple[int, str]]:
    """
    指定日の開催場を uchisankaku の raceindex.php から取得。
    「出走表」リンクを含む場が開催中。
    今日 → raceindex.php、明日 → raceindex.php?date=tomorrow
    過去日はuchisankakuのindexにパラメータが無いため、全場を候補として返す。
    """
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    if target_date == today:
        url = f"{UCHI_BASE}/raceindex.php"
    elif target_date == tomorrow:
        url = f"{UCHI_BASE}/raceindex.php?date=tomorrow"
    else:
        # 過去日・明後日以降は uchisankaku の index から特定できないため
        # 全場を返し、実際の開催有無はスケジュール取得時に判定する
        return [(jcd, name) for jcd, name in JCD_TO_NAME.items()]

    html = _fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    venues = []
    seen = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"racelist\.php\?jcode=(\d+)", a["href"])
        if not m:
            continue
        # 「出走表」リンクのみ採用（開催している場）
        if "出走表" not in a.get_text():
            continue
        jcd = int(m.group(1))
        if jcd in seen or jcd not in JCD_TO_NAME:
            continue
        seen.add(jcd)
        venues.append((jcd, JCD_TO_NAME[jcd]))
    venues.sort(key=lambda x: x[0])
    return venues


# ============================================================
# 発走時刻 (boatrace.jp)
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_venue_schedule(date_str: str, jcd: int) -> Dict[int, str]:
    jcd_str = f"{jcd:02d}"
    html = _fetch(f"{BOAT_BASE}/racelist?rno=1&jcd={jcd_str}&hd={date_str}")
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    schedule: Dict[int, str] = {}
    for a in soup.find_all("a"):
        href = a.get("href", "")
        m = re.search(r"rno=(\d+)&jcd=" + jcd_str, href)
        if not m:
            continue
        rno = int(m.group(1))
        if rno not in range(1, 13):
            continue
        txt = a.get_text(" ", strip=True)
        tm = re.search(r"(\d{1,2}):(\d{2})", txt)
        if tm:
            schedule[rno] = f"{int(tm.group(1)):02d}:{tm.group(2)}"
    return schedule


# ============================================================
# uchisankaku 出走表パーサ
# ============================================================
def _row_values(tr) -> Tuple[str, List[str]]:
    tds = tr.find_all(["td", "th"])
    if len(tds) < 6:
        return "", []
    texts = [re.sub(r"\s+", " ", td.get_text(" ").strip()) for td in tds]
    values = texts[-6:]
    labels = [t for t in texts[:-6] if t]
    label = " ".join(labels).strip()
    return label, values


@st.cache_data(ttl=300, show_spinner=False)
def fetch_uchisankaku_racelist(jcd: int, date_str: str) -> Dict[int, List[Racer]]:
    url = f"{UCHI_BASE}/racelist.php?jcode={jcd}&date={date_str}"
    html = _fetch(url)
    if not html:
        html = _fetch(f"{UCHI_BASE}/racelist.php?jcode={jcd}")
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    result: Dict[int, List[Racer]] = {}
    for h3 in soup.find_all("h3"):
        htxt = h3.get_text(" ", strip=True)
        rm = re.search(r"(\d+)R", htxt)
        if not rm:
            continue
        rno = int(rm.group(1))
        table = h3.find_next("table")
        if not table:
            continue
        racers = _parse_race_table(table)
        if racers and len(racers) == 6:
            result[rno] = racers
    return result


def _parse_race_table(table) -> List[Racer]:
    rows: List[Tuple[str, List[str]]] = []
    for tr in table.find_all("tr"):
        label, values = _row_values(tr)
        if label and values and len(values) == 6:
            rows.append((label, values))

    def pick(keywords: List[str], skip: int = 0,
             exclude: Optional[List[str]] = None) -> Optional[List[str]]:
        exclude = exclude or []
        found = 0
        for label, values in rows:
            if all(k in label for k in keywords) and not any(x in label for x in exclude):
                if found == skip:
                    return values
                found += 1
        return None

    cls_row = pick(["級別"]) or [""] * 6
    name_row = pick(["氏名"]) or [""] * 6
    weight_row = pick(["体重"]) or [""] * 6
    f_row = pick(["F数"]) or [""] * 6
    wr_natl = pick(["勝率"], skip=0) or [""] * 6

    course_st_row = None
    for label, values in rows:
        if re.search(r"\bST\b|^ST$", label) and not any(
            x in label for x in ["追い風", "向い風", "今節"]
        ):
            course_st_row = values
            break
    course_st_row = course_st_row or [""] * 6

    motor_2rate_row = None
    seen_motor = False
    for label, values in rows:
        if any(k in label for k in ["モーター", "ﾓｰﾀｰ", "モ ー タ ー"]):
            seen_motor = True
        if seen_motor and "2連率" in label and "今節" not in label:
            motor_2rate_row = values
            break
    motor_2rate_row = motor_2rate_row or [""] * 6

    settle_st_row = None
    settle_2rate_row = None
    in_settle = False
    for label, values in rows:
        if "今節" in label:
            in_settle = True
        if in_settle and re.search(r"\bST\b|^ST$", label) and settle_st_row is None:
            settle_st_row = values
        if in_settle and "2連率" in label and settle_2rate_row is None:
            settle_2rate_row = values
    settle_st_row = settle_st_row or [""] * 6
    settle_2rate_row = settle_2rate_row or [""] * 6

    racers: List[Racer] = []
    for i in range(6):
        cls_ = (cls_row[i] or "").strip()
        if cls_ not in ("A1", "A2", "B1", "B2"):
            cls_ = ""
        name = (name_row[i] or "").replace(" ", "").replace("　", "")
        win_rate = _fnum(wr_natl[i])
        course_st = _fnum(course_st_row[i])
        settle_st = _fnum(settle_st_row[i])

        s2 = _fnum(settle_2rate_row[i])
        settle_2rate = (s2 / 100.0) if (s2 is not None and s2 > 1.0) else s2
        m2 = _fnum(motor_2rate_row[i])
        motor_2rate = (m2 / 100.0) if (m2 is not None and m2 > 1.0) else m2

        fm = re.search(r"F\s*([0-2])", f_row[i] or "")
        f_count = int(fm.group(1)) if fm else 0
        weight = _fnum(weight_row[i])

        racers.append(Racer(
            name=name or f"選手{i+1}",
            cls=cls_,
            win_rate=win_rate,
            avg_st=course_st,
            settle_st=settle_st,
            settle_2rate=settle_2rate,
            motor_2rate=motor_2rate,
            f_count=f_count,
            weight=weight,
            course5_avg_st=course_st,
        ))
    return racers


# ============================================================
# レース結果 (boatrace.jp)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_race_result(date_str: str, jcd: int, rno: int) -> Optional[Dict]:
    jcd_str = f"{jcd:02d}"
    html = _fetch(f"{BOAT_BASE}/raceresult?rno={rno}&jcd={jcd_str}&hd={date_str}")
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if "まだ結果がありません" in text or "発売中" in text:
        return None

    finish_order: List[int] = []
    for tbody in soup.select("div.table1 table tbody"):
        tds = [td.get_text(strip=True) for td in tbody.find_all("td")]
        if len(tds) >= 2 and re.fullmatch(r"\d+", tds[0]) and re.fullmatch(r"[1-6]", tds[1]):
            finish_order.append(int(tds[1]))
        if len(finish_order) >= 6:
            break
    if len(finish_order) < 3:
        return None

    tri_combo, tri_payout = None, 0
    m = re.search(
        r"3連単.*?([1-6])\s*[-ー‐]\s*([1-6])\s*[-ー‐]\s*([1-6]).*?¥?\s*([\d,]+)",
        text,
    )
    if m:
        tri_combo = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        tri_payout = int(m.group(4).replace(",", ""))

    kim = None
    km = re.search(r"(逃げ|まくり差し|まくり|差し|抜き|恵まれ)", text)
    if km:
        kim = km.group(1)

    return {
        "finish_order": finish_order,
        "trifecta_combo": tri_combo,
        "trifecta_payout": tri_payout,
        "kimarite": kim,
    }


# ============================================================
# スコア & 買い目
# ============================================================
def score_all_boats(racers: List[Racer], venue: str) -> List[Dict]:
    out = []
    for i, r in enumerate(racers, start=1):
        score = score_P5(r, venue)
        out.append({
            "lane": i,
            "racer": r,
            "cls": r.cls,
            "win_rate": r.win_rate,
            "course_st": r.avg_st,
            "motor_2rate": r.motor_2rate,
            "settle_2rate": r.settle_2rate,
            "score": score,
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def generate_bets(ranked: List[Dict]) -> List[str]:
    if len(ranked) < 4:
        return []
    l1, l2, l3, l4 = [r["lane"] for r in ranked[:4]]
    bets = []
    for second in (l2, l3):
        for third in (l2, l3, l4):
            if third == second or third == l1 or second == l1:
                continue
            combo = f"{l1}-{second}-{third}"
            if combo not in bets:
                bets.append(combo)
    return bets


# ============================================================
# UI
# ============================================================
today = datetime.now().date()

col_d, col_btn = st.columns([3, 1])
with col_d:
    target_date = st.date_input(
        "日付",
        value=today,
        min_value=datetime(2020, 1, 1).date(),
        max_value=today + timedelta(days=1),
    )
with col_btn:
    st.write("")
    st.write("")
    reload_day = st.button("🔄", help="再取得")

date_str = target_date.strftime("%Y%m%d")

if reload_day:
    fetch_day_venues.clear()
    fetch_venue_schedule.clear()
    fetch_uchisankaku_racelist.clear()

with st.spinner("開催場を取得中..."):
    venues = fetch_day_venues(target_date)

if not venues:
    st.warning(f"{date_str} の開催場が見つかりません。")
    st.stop()

venue_names = [name for _, name in venues]
venue_name = st.selectbox("開催場", venue_names)
jcd = NAME_TO_JCD[venue_name]

with st.spinner("発走時刻を取得中..."):
    schedule = fetch_venue_schedule(date_str, jcd)

rno_options = []
for r in range(1, 13):
    t = schedule.get(r, "--:--")
    rno_options.append((r, f"{r}R  {t}"))

rno_choice = st.selectbox(
    "レース",
    options=[x[0] for x in rno_options],
    format_func=lambda r: next((lbl for rr, lbl in rno_options if rr == r), f"{r}R"),
)

run = st.button("🎯 解析する", type="primary", use_container_width=True)

if run:
    with st.spinner("uchisankakuから全艇データ取得中..."):
        all_races = fetch_uchisankaku_racelist(jcd, date_str)

    racers = all_races.get(rno_choice)
    if not racers or len(racers) < 6:
        st.error(
            "uchisankaku から選手データを取得できませんでした。\n\n"
            "- 指定日が節の範囲外\n"
            "- 一時的な通信障害\n"
            "- パース失敗"
        )
        st.stop()

    ranked = score_all_boats(racers, venue_name)

    is_past = (target_date < today) or (
        target_date == today
        and schedule.get(rno_choice)
        and datetime.strptime(schedule[rno_choice], "%H:%M").time() < datetime.now().time()
    )
    result = None
    if is_past:
        with st.spinner("レース結果取得中..."):
            result = fetch_race_result(date_str, jcd, rno_choice)

    # ===== 表示 =====
    st.markdown(f"### {venue_name} {rno_choice}R  {schedule.get(rno_choice, '')}")

    rows = []
    for rk, r in enumerate(ranked, start=1):
        rows.append({
            "順位": rk,
            "艇": r["lane"],
            "名前": r["racer"].name,
            "級": r["cls"] or "-",
            "勝率": f"{r['win_rate']:.2f}" if r["win_rate"] is not None else "-",
            f"{r['lane']}コST": f"{r['course_st']:.2f}" if r["course_st"] is not None else "-",
            "M2率": f"{r['motor_2rate']*100:.0f}" if r["motor_2rate"] is not None else "-",
            "節2率": f"{r['settle_2rate']*100:.0f}" if r["settle_2rate"] is not None else "-",
            "スコア": f"{r['score']:+.2f}",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    bets = generate_bets(ranked)
    if bets:
        st.subheader("🎯 推奨買い目（3連単 4点）")
        st.markdown(
            f"1位 **{ranked[0]['lane']}号艇**({ranked[0]['racer'].name}) / "
            f"2位 **{ranked[1]['lane']}号艇**({ranked[1]['racer'].name}) / "
            f"3位 **{ranked[2]['lane']}号艇**({ranked[2]['racer'].name}) / "
            f"4位 **{ranked[3]['lane']}号艇**({ranked[3]['racer'].name})"
        )
        st.code("\n".join(bets))
        st.caption("フォーメーション: 1位 - [2位,3位] - [2位,3位,4位]")

    if result:
        st.markdown("---")
        st.subheader("🏁 レース結果")
        finish = result["finish_order"]
        c1, c2 = st.columns(2)
        c1.markdown(f"**着順**: {'-'.join(str(n) for n in finish[:3])}")
        if result.get("kimarite"):
            c2.markdown(f"**決まり手**: {result['kimarite']}")

        finish_str = "-".join(str(n) for n in finish[:3])
        hit = finish_str in bets
        if result.get("trifecta_combo"):
            st.metric(
                "3連単 払戻",
                result["trifecta_combo"],
                f"¥{result.get('trifecta_payout', 0):,}",
            )

        payout = int(result.get("trifecta_payout", 0)) if hit else 0
        rr = payout / 400 * 100 if payout else 0
        profit = payout - 400
        st.markdown("### 💰 買い目収支（4点 = ¥400）")
        r1, r2, r3 = st.columns(3)
        r1.metric("投資", "¥400")
        r2.metric("回収", f"¥{payout:,}")
        r3.metric(
            "回収率",
            f"{rr:.0f}%",
            f"{profit:+,}円",
            delta_color=("normal" if rr >= 100 else "inverse"),
        )
        if hit:
            st.success(f"✅ 的中: `{finish_str}` → ¥{payout:,}")
        else:
            st.info("買い目不的中")
    elif is_past:
        st.info("結果の取得に失敗しました。")
    else:
        st.caption("🕓 このレースはまだ結果が出ていません")

    st.markdown("---")
    jcd_str = f"{jcd:02d}"
    st.markdown(
        f"🔗 [uchisankaku]({UCHI_BASE}/racelist.php?jcode={jcd}&date={date_str})  "
        f"[出走表]({BOAT_BASE}/racelist?rno={rno_choice}&jcd={jcd_str}&hd={date_str})  "
        f"[オッズ]({BOAT_BASE}/odds3t?rno={rno_choice}&jcd={jcd_str}&hd={date_str})  "
        f"[結果]({BOAT_BASE}/raceresult?rno={rno_choice}&jcd={jcd_str}&hd={date_str})"
    )
