# -*- coding: utf-8 -*-
"""
v16 全艇スコア解析アプリ（完全独立版・uchisankakuベース）
=======================================================
このファイル 1 本で動作します。依存ファイルは不要。

タブ1: 個別レース解析
タブ2: 期間バックテスト（予想1位=1号艇のレースを検索・集計）

データソース:
  - 開催場一覧 / 選手データ : uchisankaku.sakura.ne.jp
  - 結果・払戻(バックテスト): kyotei.sakura.ne.jp/kako-YYYYMMDD.html
  - 結果・払戻(個別解析)    : boatrace.jp/owpc/pc/race/raceresult

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
# データ構造・スコアリング
# ============================================================
@dataclass
class Racer:
    name: str = ""
    cls: str = ""                          # A1/A2/B1/B2
    win_rate: Optional[float] = None       # 全国勝率
    avg_st: Optional[float] = None         # コース別6ヶ月平均ST（進入コース）
    settle_st: Optional[float] = None      # 今節ST
    settle_2rate: Optional[float] = None   # 今節2連率 (0-1)
    motor_2rate: Optional[float] = None    # モーター2連率 (0-1)
    f_count: int = 0
    exhibit_rank: Optional[int] = None
    course5_avg_st: Optional[float] = None # score_P5 用（進入コースSTを格納）
    weight: Optional[float] = None
    makuri_rate: Optional[float] = None


VENUE_BONUS = {"戸田": 0.5, "江戸川": 0.5, "平和島": 0.5}


def _band(v: Optional[float],
          bands: List[Tuple[float, float, float]],
          default: float = 0.0) -> float:
    if v is None:
        return default
    for lo, hi, pts in bands:
        if lo <= v < hi:
            return pts
    return default


def score_boat(r: Racer, venue: str) -> float:
    """score_P5 のロジックを全艇に流用。course5_avg_st に進入コースSTを入れて呼ぶ。"""
    s = 0.0
    s += {"A1": 2.5, "A2": 1.5, "B1": 0.0, "B2": -1.5}.get(r.cls, 0.0)
    s += _band(r.win_rate, [(6.50, 99, 1.5), (5.50, 6.50, 1.0), (5.00, 5.50, 0.5)])
    st_val = r.course5_avg_st if r.course5_avg_st is not None else r.avg_st
    att    = 1.0             if r.course5_avg_st is not None else 0.5
    s += att * _band(st_val, [(0.00, 0.16, 1.5), (0.16, 0.18, 0.8), (0.20, 9.99, -1.0)])
    s += _band(r.settle_2rate, [(0.50, 1.01, 1.5), (0.30, 0.50, 0.5), (0.00, 0.20, -1.0)])
    if r.settle_st is not None and r.avg_st is not None and r.settle_st - r.avg_st <= -0.02:
        s += 1.0
    s += _band(r.motor_2rate, [(0.45, 1.01, 1.5), (0.30, 0.45, 0.5), (0.00, 0.25, -1.0)])
    if r.exhibit_rank == 1:   s += 1.5
    elif r.exhibit_rank == 2: s += 0.8
    elif r.exhibit_rank == 6: s -= 1.0
    if r.weight is not None:
        if r.weight <= 52.0:  s += 0.5
        elif r.weight >= 57.0: s -= 0.5
    s += VENUE_BONUS.get(venue, 0.0)
    return round(s, 2)


def rank_all(racers: List[Racer], venue: str) -> List[Dict]:
    out = [{"lane": i+1, "racer": r, "score": score_boat(r, venue)}
           for i, r in enumerate(racers)]
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def make_bets(ranked: List[Dict]) -> List[str]:
    """3連単 4点: 1位 - [2位,3位] - [2位,3位,4位]"""
    if len(ranked) < 4:
        return []
    l1, l2, l3, l4 = [x["lane"] for x in ranked[:4]]
    bets = []
    for s in (l2, l3):
        for t in (l2, l3, l4):
            if t != s and t != l1 and s != l1:
                c = f"{l1}-{s}-{t}"
                if c not in bets:
                    bets.append(c)
    return bets


# ============================================================
# 定数
# ============================================================
st.set_page_config(page_title="v16 全艇スコア解析", layout="centered")
st.title("🚤 v16 全艇スコア解析")
st.caption("進入コース別6ヶ月データで全艇評価 / uchisankaku主体")

UCHI    = "https://uchisankaku.sakura.ne.jp"
BOAT    = "https://www.boatrace.jp/owpc/pc/race"
KYOTEI  = "https://kyotei.sakura.ne.jp"
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"}

JCD_NAME = {
    1:"桐生", 2:"戸田", 3:"江戸川", 4:"平和島", 5:"多摩川", 6:"浜名湖",
    7:"蒲郡", 8:"常滑", 9:"津", 10:"三国", 11:"びわこ", 12:"住之江",
    13:"尼崎", 14:"鳴門", 15:"丸亀", 16:"児島", 17:"宮島", 18:"徳山",
    19:"下関", 20:"若松", 21:"芦屋", 22:"福岡", 23:"唐津", 24:"大村",
}
NAME_JCD = {v: k for k, v in JCD_NAME.items()}


# ============================================================
# HTTP
# ============================================================
def get(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


def fnum(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"-?\d+\.\d+|-?\d+", s)
    return float(m.group()) if m else None


# ============================================================
# uchisankaku: 開催場一覧
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def venues_for_date(d: datetime.date) -> List[Tuple[int, str]]:
    today = datetime.now().date()
    if d == today:
        url = f"{UCHI}/raceindex.php"
    elif d == today + timedelta(days=1):
        url = f"{UCHI}/raceindex.php?date=tomorrow"
    else:
        # 過去日は全場を候補として返す
        return list(JCD_NAME.items())

    html = get(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    seen, result = set(), []
    for a in soup.find_all("a", href=True):
        m = re.search(r"racelist\.php\?jcode=(\d+)", a["href"])
        if not m or "出走表" not in a.get_text():
            continue
        jcd = int(m.group(1))
        if jcd not in seen and jcd in JCD_NAME:
            seen.add(jcd)
            result.append((jcd, JCD_NAME[jcd]))
    result.sort(key=lambda x: x[0])
    return result


# ============================================================
# uchisankaku: 出走表パーサ
# ============================================================
def _tr_label_vals(tr) -> Tuple[str, List[str]]:
    tds = tr.find_all(["td", "th"])
    if len(tds) < 6:
        return "", []
    txts = [re.sub(r"\s+", " ", td.get_text(" ").strip()) for td in tds]
    return " ".join(t for t in txts[:-6] if t), txts[-6:]


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_racelist_html(jcd: int, date_str: str) -> Optional[str]:
    html = get(f"{UCHI}/racelist.php?jcode={jcd}&date={date_str}")
    if not html:
        html = get(f"{UCHI}/racelist.php?jcode={jcd}")
    return html


def fetch_racelist(jcd: int, date_str: str) -> Dict[int, List[Racer]]:
    html = _fetch_racelist_html(jcd, date_str)
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    out: Dict[int, List[Racer]] = {}
    for h3 in soup.find_all("h3"):
        m = re.search(r"(\d+)R", h3.get_text(" ", strip=True))
        if not m:
            continue
        rno = int(m.group(1))
        tbl = h3.find_next("table")
        if tbl:
            racers = _parse_table(tbl)
            if len(racers) == 6:
                out[rno] = racers
    return out


def _parse_table(table) -> List[Racer]:
    rows = []
    for tr in table.find_all("tr"):
        lbl, vals = _tr_label_vals(tr)
        if lbl and vals and len(vals) == 6:
            rows.append((lbl, vals))

    def pick(keys, skip=0, excl=None):
        excl = excl or []
        n = 0
        for lbl, vals in rows:
            if all(k in lbl for k in keys) and not any(e in lbl for e in excl):
                if n == skip:
                    return vals
                n += 1
        return None

    cls_r   = pick(["級別"])             or [""]*6
    name_r  = pick(["氏名"])             or [""]*6
    wt_r    = pick(["体重"])             or [""]*6
    f_r     = pick(["F数"])              or [""]*6
    wr_r    = pick(["勝率"], skip=0)     or [""]*6

    # コース別6ヶ月ST
    cst_r = None
    for lbl, vals in rows:
        if re.search(r"\bST\b|^ST$", lbl) and not any(
                x in lbl for x in ["追い風", "向い風", "今節"]):
            cst_r = vals
            break
    cst_r = cst_r or [""]*6

    # モーター2連率
    m2_r, in_motor = None, False
    for lbl, vals in rows:
        if any(k in lbl for k in ["モーター", "モ ー タ ー"]):
            in_motor = True
        if in_motor and "2連率" in lbl and "今節" not in lbl:
            m2_r = vals
            break
    m2_r = m2_r or [""]*6

    # 今節 ST・2連率
    sst_r, s2_r, in_s = None, None, False
    for lbl, vals in rows:
        if "今節" in lbl:
            in_s = True
        if in_s and re.search(r"\bST\b|^ST$", lbl) and sst_r is None:
            sst_r = vals
        if in_s and "2連率" in lbl and s2_r is None:
            s2_r = vals
    sst_r = sst_r or [""]*6
    s2_r  = s2_r  or [""]*6

    racers = []
    for i in range(6):
        cls_ = (cls_r[i] or "").strip()
        if cls_ not in ("A1", "A2", "B1", "B2"):
            cls_ = ""
        name   = (name_r[i] or "").replace(" ", "").replace("　", "")
        cst    = fnum(cst_r[i])
        sst    = fnum(sst_r[i])
        s2v    = fnum(s2_r[i])
        s2     = (s2v/100.0) if (s2v and s2v > 1.0) else s2v
        m2v    = fnum(m2_r[i])
        m2     = (m2v/100.0) if (m2v and m2v > 1.0) else m2v
        fm     = re.search(r"F\s*([0-2])", f_r[i] or "")
        racers.append(Racer(
            name=name or f"選手{i+1}", cls=cls_,
            win_rate=fnum(wr_r[i]), avg_st=cst,
            settle_st=sst, settle_2rate=s2,
            motor_2rate=m2, f_count=int(fm.group(1)) if fm else 0,
            weight=fnum(wt_r[i]), course5_avg_st=cst,
        ))
    return racers


# ============================================================
# kyotei.sakura.ne.jp: 1日分の払戻を一括取得
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_kyotei_day(date_str: str) -> Dict[Tuple[int, int], int]:
    html = get(f"{KYOTEI}/kako-{date_str}.html")
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    payouts: Dict[Tuple[int, int], int] = {}
    pat = re.compile(r'info-\d{8}-(\d+)-(\d+)\.html')
    for a in soup.find_all("a", href=True):
        if "race.kyotei.club" not in a["href"]:
            continue
        m = pat.search(a["href"])
        if not m:
            continue
        jcd = int(m.group(1))
        rno = int(m.group(2))
        if jcd not in JCD_NAME or rno not in range(1, 13):
            continue
        if (jcd, rno) in payouts:
            continue
        tr = a.find_parent("tr")
        if not tr:
            continue
        for a2 in tr.find_all("a", href=True):
            if "info.kyotei.fun" not in a2["href"]:
                continue
            txt = a2.get_text(strip=True).replace(",", "")
            if re.fullmatch(r"\d+", txt) and int(txt) > 0:
                payouts[(jcd, rno)] = int(txt)
                break
    return payouts


def kyotei_venues(date_str: str) -> List[int]:
    html = get(f"{KYOTEI}/kako-{date_str}.html")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    jcds = []
    for t in soup.find_all(string=re.compile(r'#\s*\d+')):
        for m in re.finditer(r'#\s*(\d+)', t):
            j = int(m.group(1))
            if j in JCD_NAME and j not in jcds:
                jcds.append(j)
    jcds.sort()
    return jcds


# ============================================================
# boatrace.jp: 個別レース着順・払戻
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_result(date_str: str, jcd: int, rno: int) -> Optional[Dict]:
    jcd_s = f"{jcd:02d}"
    html  = get(f"{BOAT}/raceresult?rno={rno}&jcd={jcd_s}&hd={date_str}")
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if "まだ結果がありません" in text or "発売中" in text:
        return None

    finish: List[int] = []
    for tbody in soup.select("div.table1 table tbody"):
        tds = [td.get_text(strip=True) for td in tbody.find_all("td")]
        if len(tds) >= 2 and re.fullmatch(r"\d+", tds[0]) and re.fullmatch(r"[1-6]", tds[1]):
            finish.append(int(tds[1]))
        if len(finish) >= 6:
            break
    if len(finish) < 3:
        return None

    combo, pay = None, 0
    m = re.search(r"3連単.*?([1-6])\s*[-ー‐]\s*([1-6])\s*[-ー‐]\s*([1-6]).*?¥?\s*([\d,]+)", text)
    if m:
        combo = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        pay   = int(m.group(4).replace(",", ""))

    kim = None
    km = re.search(r"(逃げ|まくり差し|まくり|差し|抜き|恵まれ)", text)
    if km:
        kim = km.group(1)

    return {"finish": finish, "combo": combo, "payout": pay, "kimarite": kim}


# ============================================================
# UI
# ============================================================
today = datetime.now().date()
tab1, tab2 = st.tabs(["🔍 1レース解析", "📊 期間バックテスト"])


# ──────────────────────────────────────────────────────────
# TAB 1: 個別レース解析
# ──────────────────────────────────────────────────────────
with tab1:
    c1, c2 = st.columns([3, 1])
    with c1:
        t1_date = st.date_input(
            "日付", value=today,
            min_value=datetime(2020,1,1).date(),
            max_value=today + timedelta(days=1),
            key="t1_date",
        )
    with c2:
        st.write("")
        st.write("")
        if st.button("🔄", key="t1_reload"):
            st.cache_data.clear()

    dstr = t1_date.strftime("%Y%m%d")

    with st.spinner("開催場を取得中..."):
        vlist = venues_for_date(t1_date)

    if not vlist:
        st.warning("開催場が見つかりません。")
    else:
        vname = st.selectbox("開催場", [n for _, n in vlist], key="t1_venue")
        jcd   = NAME_JCD[vname]
        rno   = st.selectbox("レース", list(range(1, 13)),
                             format_func=lambda r: f"{r}R", key="t1_rno")

        if st.button("🎯 解析する", type="primary", use_container_width=True, key="t1_run"):
            with st.spinner("選手データ取得中..."):
                all_r = fetch_racelist(jcd, dstr)

            racers = all_r.get(rno)
            if not racers or len(racers) < 6:
                st.error("選手データを取得できませんでした。時間をおいて再試行してください。")
            else:
                ranked = rank_all(racers, vname)
                bets   = make_bets(ranked)

                res = None
                if t1_date <= today:
                    with st.spinner("レース結果取得中..."):
                        res = fetch_result(dstr, jcd, rno)

                # ── スコアテーブル ──
                st.markdown(f"### {vname} {rno}R")
                df_rows = []
                for rk, x in enumerate(ranked, 1):
                    r = x["racer"]
                    
                    # スマホでのコピペ時に改行が混ざらないよう、事前にフォーマットして変数に入れます
                    win_r = f"{r.win_rate:.2f}" if r.win_rate is not None else "-"
                    c_st  = f"{r.avg_st:.2f}" if r.avg_st is not None else "-"
                    m2_r  = f"{r.motor_2rate*100:.0f}" if r.motor_2rate is not None else "-"
                    s2_r  = f"{r.settle_2rate*100:.0f}" if r.settle_2rate is not None else "-"
                    sc_s  = f"{x['score']:+.2f}"
                    
                    df_rows.append({
                        "順位": rk,
                        "艇": x["lane"],
                        "名前": r.name,
                        "級": r.cls or "-",
                        "勝率": win_r,
                        "コースST": c_st,
                        "M2率": m2_r,
                        "節2率": s2_r,
                        "スコア": sc_s,
                    })
                st.dataframe(pd.DataFrame(df_rows), use_container_width=True, hide_index=True)

                # ── 買い目 ──
                if bets:
                    st.subheader("🎯 推奨買い目（3連単 4点）")
                    st.markdown(
                        " / ".join(
                            f"**{i+1}位** {ranked[i]['lane']}号艇({ranked[i]['racer'].name})"
                            for i in range(4)
                        )
                    )
                    st.code("\n".join(bets))
                    st.caption("フォーメーション: 1位-[2位,3位]-[2位,3位,4位]")

                # ── 結果 ──
                if res:
                    st.markdown("---")
                    st.subheader("🏁 レース結果")
                    c1r, c2r = st.columns(2)
                    c1r.markdown(f"**着順**: {'-'.join(str(n) for n in res['finish'][:3])}")
                    if res.get("kimarite"):
                        c2r.markdown(f"**決まり手**: {res['kimarite']}")
                    hit     = res["combo"] in bets if res["combo"] else False
                    payout  = res["payout"] if hit else 0
                    rr      = payout / 400 * 100
                    profit  = payout - 400
                    if res.get("combo"):
                        st.metric("3連単 払戻", res["combo"], f"¥{res['payout']:,}")
                    st.markdown("### 💰 買い目収支（4点=¥400）")
                    ca, cb, cc = st.columns(3)
                    ca.metric("投資", "¥400")
                    cb.metric("回収", f"¥{payout:,}")
                    cc.metric("回収率", f"{rr:.0f}%", f"{profit:+,}円",
                              delta_color="normal" if rr >= 100 else "inverse")
                    if hit:
                        st.success(f"✅ 的中: `{res['combo']}` → ¥{payout:,}")
                    else:
                        st.info("買い目不的中")
                else:
                    st.caption("🕓 結果未確定（未発走または取得失敗）")

                jcd_s = f"{jcd:02d}"
                st.markdown("---")
                st.markdown(
                    f"🔗 [uchisankaku]({UCHI}/racelist.php?jcode={jcd}&date={dstr})  "
                    f"[出走表]({BOAT}/racelist?rno={rno}&jcd={jcd_s}&hd={dstr})  "
                    f"[オッズ]({BOAT}/odds3t?rno={rno}&jcd={jcd_s}&hd={dstr})  "
                    f"[結果]({BOAT}/raceresult?rno={rno}&jcd={jcd_s}&hd={dstr})"
                )


# ──────────────────────────────────────────────────────────
# TAB 2: 期間バックテスト
# ──────────────────────────────────────────────────────────
with tab2:
    st.subheader("📊 期間バックテスト")
    st.caption("予想スコア1位が1号艇のレースを全場・全Rで抽出して集計します。")

    bc1, bc2 = st.columns(2)
    with bc1:
        bt_s = st.date_input(
            "開始日", value=today - timedelta(days=7),
            min_value=datetime(2020,1,1).date(),
            max_value=today - timedelta(days=1),
            key="bt_s",
        )
    with bc2:
        bt_e = st.date_input(
            "終了日", value=today - timedelta(days=1),
            min_value=datetime(2020,1,1).date(),
            max_value=today - timedelta(days=1),
            key="bt_e",
        )

    if bt_s > bt_e:
        st.warning("開始日 ≤ 終了日 にしてください。")
    else:
        n_days = (bt_e - bt_s).days + 1
        st.caption(
            f"対象: {bt_s} 〜 {bt_e}（{n_days}日間）  "
            "結果は kyotei.sakura.ne.jp から取得（1日1リクエスト）"
        )

        if st.button("🔍 1号艇1位を検索", type="primary",
                     use_container_width=True, key="bt_run"):
            days     = [bt_s + timedelta(days=i) for i in range(n_days)]
            prog     = st.progress(0.0)
            status   = st.empty()
            matches: List[Dict] = []

            for idx, day in enumerate(days):
                dstr_bt = day.strftime("%Y%m%d")
                prog.progress((idx + 1) / n_days,
                              text=f"[{idx+1}/{n_days}] {dstr_bt} 処理中...")

                # ① kyotei から払戻を一括取得
                status.caption(f"📡 {dstr_bt} — kyotei 払戻取得中...")
                payouts = fetch_kyotei_day(dstr_bt)
                if not payouts:
                    continue

                # kyotei ページから開催場を特定
                open_jcds = kyotei_venues(dstr_bt)
                if not open_jcds:
                    open_jcds = sorted({jcd for jcd, _ in payouts.keys()})

                # ② 場ごとに選手データ取得→スコアリング
                for jcd_bt in open_jcds:
                    venue_bt = JCD_NAME.get(jcd_bt, "")
                    if not venue_bt:
                        continue
                    status.caption(f"📡 {dstr_bt} {venue_bt} — 選手データ取得中...")
                    races = fetch_racelist(jcd_bt, dstr_bt)
                    if not races:
                        continue

                    for rno_bt, racers_bt in sorted(races.items()):
                        if len(racers_bt) < 6:
                            continue
                        ranked_bt = rank_all(racers_bt, venue_bt)
                        if ranked_bt[0]["lane"] != 1:
                            continue   # 予想1位が1号艇でない

                        bets_bt    = make_bets(ranked_bt)
                        top_score  = ranked_bt[0]["score"]
                        pay_kyotei = payouts.get((jcd_bt, rno_bt))

                        if pay_kyotei is None:
                            # kyotei に払戻なし = 未終了 or 返還
                            matches.append({
                                "日付": dstr_bt, "場": venue_bt, "R": rno_bt,
                                "スコア": top_score, "_bets": bets_bt,
                                "結果": "未確定", "払戻": 0,
                                "_hit": None, "_payout": 0,
                            })
                            continue

                        # ③ 着順確認（boatrace.jp: マッチ済みレースのみ）
                        status.caption(
                            f"📡 {dstr_bt} {venue_bt} {rno_bt}R — 着順確認...")
                        res_bt = fetch_result(dstr_bt, jcd_bt, rno_bt)
                        if res_bt and res_bt["combo"]:
                            combo_bt = res_bt["combo"]
                            hit_bt   = combo_bt in bets_bt
                            payout_bt = pay_kyotei if hit_bt else 0
                        else:
                            combo_bt = "取得失敗"
                            hit_bt   = None
                            payout_bt = 0

                        matches.append({
                            "日付": dstr_bt, "場": venue_bt, "R": rno_bt,
                            "スコア": top_score, "_bets": bets_bt,
                            "結果": combo_bt, "払戻": pay_kyotei,
                            "_hit": hit_bt, "_payout": payout_bt,
                        })

            prog.empty()
            status.empty()
            st.session_state["bt_matches"] = matches

        # ── 結果表示 ──
        if "bt_matches" in st.session_state:
            M = st.session_state["bt_matches"]
            if not M:
                st.warning("対象期間に予想1位=1号艇のレースが見つかりませんでした。")
            else:
                fin   = [m for m in M if m["_hit"] is not None]
                hits  = [m for m in fin if m["_hit"] is True]
                n_tot = len(M)
                n_fin = len(fin)
                n_hit = len(hits)
                inv   = n_fin * 400
                ret   = sum(m["_payout"] for m in fin)
                rr    = round(ret / inv * 100, 1) if inv > 0 else 0
                hr    = round(n_hit / n_fin * 100, 1) if n_fin > 0 else 0

                st.success(f"✅ {n_tot}件 抽出（結果確定: {n_fin}件）")

                st.markdown("### 📊 集計")
                ca, cb, cc, cd = st.columns(4)
                ca.metric("対象",   f"{n_tot}件")
                cb.metric("的中",   f"{n_hit}/{n_fin}", f"{hr}%")
                cc.metric("回収率", f"{rr}%",
                          f"{ret-inv:+,}円",
                          delta_color="normal" if rr >= 100 else "inverse")
                cd.metric("投資/回収", f"¥{inv:,} / ¥{ret:,}")

                st.markdown("### 📋 レース一覧")
                rows_disp = []
                for m in M:
                    if m["_hit"] is True:  mk = "✅"
                    elif m["_hit"] is False: mk = "✕"
                    else: mk = "-"
                    rows_disp.append({
                        "日付":    m["日付"],
                        "場":      m["場"],
                        "R":       m["R"],
                        "スコア":  f"{m['スコア']:+.2f}",
                        "買い目":  " ".join(m["_bets"]),
                        "結果":    m["結果"],
                        "払戻":    f"¥{m['払戻']:,}" if m["払戻"] else "-",
                        "的中":    mk,
                        "回収率":  f"{m['_payout']/400*100:.0f}%"
                                  if m["_hit"] is True else ("-" if m["_hit"] is None else "0%"),
                    })
                st.dataframe(pd.DataFrame(rows_disp),
                             use_container_width=True, hide_index=True)
