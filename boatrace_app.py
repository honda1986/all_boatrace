"""
🚤 ボートレース予想アプリ v3
━━━━━━━━━━━━━━━━━━━━━━━━
Streamlit ベースの競艇スコアリング予想システム

起動方法:
  pip install streamlit requests beautifulsoup4 lxml pandas
  streamlit run boatrace_app.py
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, date, timedelta
import time
import pandas as pd

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 定数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VENUES = {
    "01": {"name": "桐生",   "region": "関東", "in_adj": -1.5, "rough": False},
    "02": {"name": "戸田",   "region": "関東", "in_adj": -3.0, "rough": True},
    "03": {"name": "江戸川", "region": "関東", "in_adj": -3.0, "rough": True},
    "04": {"name": "平和島", "region": "関東", "in_adj": -3.0, "rough": True},
    "05": {"name": "多摩川", "region": "関東", "in_adj": -1.5, "rough": False},
    "06": {"name": "浜名湖", "region": "東海", "in_adj": 0,    "rough": False},
    "07": {"name": "蒲郡",   "region": "東海", "in_adj": 0,    "rough": False},
    "08": {"name": "常滑",   "region": "東海", "in_adj": 0,    "rough": False},
    "09": {"name": "津",     "region": "東海", "in_adj": 0,    "rough": False},
    "10": {"name": "三国",   "region": "北陸", "in_adj": 0,    "rough": False},
    "11": {"name": "びわこ", "region": "近畿", "in_adj": -1.5, "rough": False},
    "12": {"name": "住之江", "region": "近畿", "in_adj": 1.5,  "rough": False},
    "13": {"name": "尼崎",   "region": "近畿", "in_adj": 0,    "rough": False},
    "14": {"name": "鳴門",   "region": "四国", "in_adj": 0,    "rough": False},
    "15": {"name": "丸亀",   "region": "四国", "in_adj": 1.5,  "rough": False},
    "16": {"name": "児島",   "region": "中国", "in_adj": 0,    "rough": False},
    "17": {"name": "宮島",   "region": "中国", "in_adj": 0,    "rough": False},
    "18": {"name": "徳山",   "region": "中国", "in_adj": 3.0,  "rough": False},
    "19": {"name": "下関",   "region": "中国", "in_adj": 1.5,  "rough": False},
    "20": {"name": "若松",   "region": "九州", "in_adj": 0,    "rough": False},
    "21": {"name": "芦屋",   "region": "九州", "in_adj": 3.0,  "rough": False},
    "22": {"name": "福岡",   "region": "九州", "in_adj": 0,    "rough": False},
    "23": {"name": "唐津",   "region": "九州", "in_adj": 0,    "rough": False},
    "24": {"name": "大村",   "region": "九州", "in_adj": 3.0,  "rough": False},
}

COURSE_COLORS_CSS = {
    1: "background:#FFF;color:#000;border:1.5px solid #999;",
    2: "background:#000;color:#FFF;",
    3: "background:#E8212A;color:#FFF;",
    4: "background:#1B6DB5;color:#FFF;",
    5: "background:#F5C518;color:#000;",
    6: "background:#2D8C3C;color:#FFF;",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# スクレイピング
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@st.cache_data(ttl=300)
def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    return resp.text


def get_active_venues(date_str: str) -> list:
    """指定日に開催中の場を取得"""
    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={hd}"
    try:
        html = fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")
        active, seen = [], set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "raceindex" in href and f"hd={hd}" in href:
                m = re.search(r"jcd=(\d{2})", href)
                if m:
                    jcd = m.group(1)
                    if jcd in VENUES and jcd not in seen:
                        seen.add(jcd)
                        active.append({
                            "jcd": jcd,
                            "name": VENUES[jcd]["name"],
                            "region": VENUES[jcd]["region"],
                            "in_adj": VENUES[jcd]["in_adj"],
                        })
        return active
    except Exception as e:
        st.error(f"開催場の取得に失敗: {e}")
        return []


def get_race_times(jcd: str, date_str: str) -> dict:
    """各レースの締切予定時刻を取得"""
    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={jcd}&hd={hd}"
    times = {}
    try:
        html = fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()

        # 時刻パターン全抽出 (HH:MM)
        all_times = re.findall(r'(\d{1,2}:\d{2})', text)
        # 発走時刻帯(8:00-21:00)のものだけ、重複排除
        valid = []
        for t in all_times:
            h = int(t.split(":")[0])
            if 8 <= h <= 21 and t not in valid:
                valid.append(t)
        # 先頭12個をレース番号に割当
        for i, t in enumerate(valid[:12]):
            times[i + 1] = t
    except Exception:
        pass
    return times


def get_race_card(jcd: str, date_str: str, race_no: int) -> list:
    """出走表データを取得"""
    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_no}&jcd={jcd}&hd={hd}"
    try:
        html = fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")
        return parse_racelist(soup)
    except Exception as e:
        st.error(f"出走表の取得に失敗: {e}")
        return []


def parse_racelist(soup: BeautifulSoup) -> list:
    """出走表HTMLをパース（修正版: 選手データのtbodyのみ抽出）"""
    racers = []
    all_tbody = soup.find_all("tbody")

    # 選手データを含む tbody を特定
    # → 登録番号(4桁) と 級別(A1/A2/B1/B2) の両方を含むもの
    racer_tbodies = []
    for tb in all_tbody:
        tb_text = tb.get_text()
        has_reg = bool(re.search(r'\b\d{4}\b', tb_text))
        has_class = bool(re.search(r'\b[AB][12]\b', tb_text))
        if has_reg and has_class:
            racer_tbodies.append(tb)

    for course_num, tbody in enumerate(racer_tbodies[:6], 1):
        racer = extract_racer(tbody, course_num)
        racers.append(racer)

    while len(racers) < 6:
        c = len(racers) + 1
        racers.append(make_dummy(c))

    return racers


def extract_racer(tbody, course: int) -> dict:
    """個別tbodyから選手情報を抽出"""
    racer = {"course": course}
    text = tbody.get_text(separator="|", strip=True)
    cells = [c.strip() for c in text.split("|") if c.strip()]

    # 登録番号(4桁)
    reg = "----"
    for c in cells:
        if re.match(r'^\d{4}$', c):
            reg = c
            break

    # 選手名(漢字2-4文字, 地名除外)
    EXCLUDE = {
        "東京","大阪","福岡","愛知","埼玉","群馬","静岡","長崎","広島","岡山",
        "山口","三重","徳島","香川","佐賀","熊本","千葉","茨城","栃木","長野",
        "新潟","富山","石川","福井","滋賀","京都","兵庫","奈良","鳥取","島根",
        "高知","愛媛","宮崎","鹿児島","沖縄","北海道","青森","岩手","宮城",
        "秋田","山形","福島","山梨","岐阜","大分","和歌山","神奈川",
    }
    name = f"選手{course}"
    for c in cells:
        c2 = c.replace(" ", "").replace("　", "")
        if 2 <= len(c2) <= 4 and re.match(r'^[一-龥ぁ-んァ-ヴー]+$', c2) and c2 not in EXCLUDE:
            name = c2
            break

    # 級別
    cls = "B1"
    for c in cells:
        if c.strip() in ("A1", "A2", "B1", "B2"):
            cls = c.strip()
            break

    all_nums = re.findall(r'\d+\.?\d*', text)

    # 年齢(18-70)
    age = 35
    for n in all_nums:
        v = float(n)
        if 18 <= v <= 70 and v == int(v):
            age = int(v)
            break

    # 勝率(X.XX形式, 2.00-10.00)
    rates = []
    for n in all_nums:
        if re.match(r'^\d\.\d{2}$', n):
            v = float(n)
            if 2.0 <= v <= 10.0:
                rates.append(v)
    nr = rates[0] if rates else 5.0
    lr = rates[1] if len(rates) >= 2 else nr

    # モーター2連率(XX.X%)
    motor = 33.0
    for n in all_nums:
        if re.match(r'^\d{2}\.\d$', n):
            v = float(n)
            if 15 <= v <= 75 and v != nr and v != lr:
                motor = v
                break

    # F数
    fc = 0
    fm = re.search(r'F(\d)', text)
    if fm:
        fc = int(fm.group(1))

    # 平均ST(0.XX)
    avg_st = 0.15
    for n in all_nums:
        if re.match(r'^0\.\d{2}$', n):
            v = float(n)
            if 0.01 <= v <= 0.40:
                avg_st = v
                break

    racer.update({
        "number": reg, "name": name, "class": cls, "age": age,
        "national_rate": nr, "local_rate": lr, "motor_2ren": motor,
        "f_count": fc, "avg_st": avg_st,
    })
    return racer


def make_dummy(c):
    return {"course": c, "number": "----", "name": f"選手{c}", "class": "B1",
            "age": 30, "national_rate": 5.0, "local_rate": 5.0,
            "motor_2ren": 33.0, "f_count": 0, "avg_st": 0.15}


def get_before_info(jcd: str, date_str: str, race_no: int) -> dict:
    """直前情報を取得"""
    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={race_no}&jcd={jcd}&hd={hd}"
    result = {"weather": {"wind_dir": "", "wind_speed": 0, "wave": 0}, "exhibition_times": {}}
    try:
        html = fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)

        # 風向き
        for wd in ["追い風", "向かい風", "右横風", "左横風"]:
            if wd in text:
                result["weather"]["wind_dir"] = wd
                break

        # 風速 (Xm だが 1800m 等の距離を除外)
        for m in re.finditer(r'(?<!\d)(\d{1,2})m(?![0-9])', text):
            ws = int(m.group(1))
            if 0 < ws <= 15:
                result["weather"]["wind_speed"] = ws
                break

        # 波高
        wm = re.search(r'(\d{1,2})\s*cm', text)
        if wm:
            result["weather"]["wave"] = int(wm.group(1))

        # 展示タイム(6.XX or 7.XX)
        ex = re.findall(r'\b(6\.\d{2}|7\.\d{2})\b', text)
        for i, t in enumerate(ex[:6]):
            result["exhibition_times"][i + 1] = float(t)
    except Exception:
        pass
    return result


def get_race_result(jcd: str, date_str: str, race_no: int) -> dict:
    """レース結果と払戻金を取得"""
    hd = date_str.replace("-", "")
    res = {"has_result": False, "order": [], "payouts": []}
    soup = None
    soup2 = None

    # ── 1. 結果ページから着順を取得 ──
    result_url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_no}&jcd={jcd}&hd={hd}"
    try:
        html = fetch_page(result_url)
        soup = BeautifulSoup(html, "html.parser")
        full = soup.get_text(separator="|", strip=True)

        if "着" not in full and "結果" not in full:
            return res
        res["has_result"] = True

        # 着順取得 - tbody内のtr行を走査
        for tb in soup.find_all("tbody"):
            for tr in tb.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    row_text = tr.get_text(separator=" ", strip=True)
                    rm = re.match(r'^(\d)\s', row_text)
                    if rm:
                        rank = int(rm.group(1))
                        if 1 <= rank <= 6:
                            frame_m = re.search(r'\b([1-6])\b', row_text[2:10])
                            frame = int(frame_m.group(1)) if frame_m else 0
                            nm = re.search(r'([一-龥ぁ-んァ-ヴー]{2,4})', row_text)
                            reg = re.search(r'(\d{4})', row_text)
                            res["order"].append({
                                "rank": rank, "frame": frame,
                                "name": nm.group(1) if nm else "",
                                "reg": reg.group(1) if reg else "",
                            })

        # 重複除去＋ソート
        seen = set()
        unique = []
        for o in sorted(res["order"], key=lambda x: x["rank"]):
            if o["rank"] not in seen:
                seen.add(o["rank"])
                unique.append(o)
        res["order"] = unique[:6]

    except Exception:
        pass

    # ── 2. 払戻金ページから払戻を取得（専用URL） ──
    payoff_url = f"https://www.boatrace.jp/owpc/pc/race/payoff?rno={race_no}&jcd={jcd}&hd={hd}"
    try:
        html2 = fetch_page(payoff_url)
        soup2 = BeautifulSoup(html2, "html.parser")
        _parse_payouts(soup2, res)
    except Exception:
        pass

    # 払戻金が取れなかった場合、結果ページからも再取得を試行
    if not res["payouts"]:
        try:
            html3 = fetch_page(result_url)
            soup3 = BeautifulSoup(html3, "html.parser")
            _parse_payouts(soup3, res)
        except Exception:
            pass

    # それでも取れない場合、全テキストからの正規表現フォールバック
    if not res["payouts"]:
        try:
            full_text = ""
            try:
                full_text += soup.get_text(separator="\n", strip=True)
            except Exception:
                pass
            try:
                full_text += "\n" + soup2.get_text(separator="\n", strip=True)
            except Exception:
                pass
            if full_text.strip():
                _parse_payouts_from_text(full_text, res)
        except Exception:
            pass

    return res


def _parse_payouts(soup: BeautifulSoup, res: dict):
    """払戻金テーブルをパース（複数方式で試行）"""
    seen = {f"{p['type']}_{p['combo']}" for p in res["payouts"]}
    bet_types = ["3連単", "3連複", "2連単", "2連複", "拡連複", "単勝", "複勝"]

    # 方式1: テーブル行を1つずつ走査し、券種→組番→金額の順でセルを読む
    for tbl in soup.find_all("table"):
        rows = tbl.find_all("tr")
        current_bet_type = ""
        for tr in rows:
            cells = tr.find_all(["td", "th"])
            cell_texts = [c.get_text(strip=True) for c in cells]
            row_text = " ".join(cell_texts)

            # 券種を検出
            for bt in bet_types:
                if bt in row_text:
                    current_bet_type = bt
                    break

            if not current_bet_type:
                continue

            # 組番パターン: "1-2-3", "1=2=3", "1-2", "1=2", 全角ダッシュ含む
            combo_m = re.search(r'(\d[\s]*[-=＝ー－–][\s]*\d(?:[\s]*[-=＝ー－–][\s]*\d)?)', row_text)
            # 金額パターン: カンマ区切りの数字 + "円"
            amount_m = re.search(r'([\d,]+)\s*円', row_text)

            # 単勝・複勝は組番が1桁のみの場合もある
            if not combo_m and current_bet_type in ("単勝", "複勝"):
                combo_m2 = re.search(r'\b([1-6])\b', row_text)
                if combo_m2 and amount_m:
                    combo = combo_m2.group(1)
                    amt = amount_m.group(1).replace(",", "")
                    key = f"{current_bet_type}_{combo}"
                    if key not in seen and amt.isdigit():
                        seen.add(key)
                        res["payouts"].append({
                            "type": current_bet_type,
                            "combo": combo,
                            "amount": int(amt),
                        })

            if combo_m and amount_m:
                combo = re.sub(r'[\s＝ー－–]', '-', combo_m.group(1)).replace('=', '-')
                amt = amount_m.group(1).replace(",", "")
                key = f"{current_bet_type}_{combo}"
                if key not in seen and amt.isdigit():
                    seen.add(key)
                    res["payouts"].append({
                        "type": current_bet_type,
                        "combo": combo,
                        "amount": int(amt),
                    })

    # 方式2: テーブルテキスト全体をパイプ区切りで解析
    if not res["payouts"]:
        for tbl in soup.find_all("table"):
            tbl_text = tbl.get_text(separator="|", strip=True)
            for bt in bet_types:
                # 「3連単|...|1-2-3|...|12,345円」のようなパターン
                patterns = [
                    rf'{bt}[|]+.*?(\d[\d\-=＝]+\d)[|]+([\d,]+)円',
                    rf'{bt}.*?(\d\s*[-=＝]\s*\d\s*[-=＝]\s*\d)\s*[\|]?\s*([\d,]+)\s*円',
                    rf'{bt}.*?(\d\s*[-=＝]\s*\d)\s*[\|]?\s*([\d,]+)\s*円',
                ]
                for pat in patterns:
                    for m in re.finditer(pat, tbl_text):
                        combo = re.sub(r'[\s＝]', '-', m.group(1)).replace('=', '-')
                        amt = m.group(2).replace(",", "")
                        key = f"{bt}_{combo}"
                        if key not in seen and amt.isdigit():
                            seen.add(key)
                            res["payouts"].append({
                                "type": bt, "combo": combo, "amount": int(amt),
                            })


def _parse_payouts_from_text(text: str, res: dict):
    """プレーンテキストから払戻金を正規表現で抽出（最終フォールバック）"""
    seen = {f"{p['type']}_{p['combo']}" for p in res["payouts"]}
    bet_types = ["3連単", "3連複", "2連単", "2連複", "拡連複", "単勝", "複勝"]

    for bt in bet_types:
        # 券種名の後に出現する 組番+金額 のペアを探す
        # bt が出現する位置から先の200文字を対象に
        for m_bt in re.finditer(re.escape(bt), text):
            chunk = text[m_bt.start():m_bt.start() + 300]
            # 組番(X-X-X or X-X) + 金額
            combos = re.findall(
                r'(\d[\s]*[-=＝ー－–][\s]*\d(?:[\s]*[-=＝ー－–][\s]*\d)?)'
                r'[^\d]*?([\d,]{3,})\s*円',
                chunk
            )
            for combo_raw, amt_raw in combos:
                combo = re.sub(r'[\s＝ー－–=]', '-', combo_raw)
                amt = amt_raw.replace(",", "")
                key = f"{bt}_{combo}"
                if key not in seen and amt.isdigit():
                    seen.add(key)
                    res["payouts"].append({
                        "type": bt, "combo": combo, "amount": int(amt),
                    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# v3 スコアリングエンジン
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calc_scores(racers, venue_jcd, weather, exhibition_times,
                is_day1=False, is_final=False):
    venue = VENUES[venue_jcd]
    scored = []

    ex_sorted = sorted(exhibition_times.items(), key=lambda x: x[1]) if exhibition_times else []
    ex_rank = {course: rank for rank, (course, _) in enumerate(ex_sorted, 1)}

    for r in racers:
        c = r["course"]
        sc = {}
        notes = []

        # ① コース基礎
        s = {1: 7, 2: 5, 3: 4, 4: 3.5, 5: 3, 6: 1.5}.get(c, 3)
        if is_final and c == 1:
            s = 12; notes.append("優勝戦1C")
        sc["コース基礎"] = s

        # ② 場別イン
        sc["場別イン"] = venue["in_adj"] if c == 1 else 0

        # ③ 風速波高
        s3 = 0
        ws = weather.get("wind_speed", 0)
        wd = weather.get("wind_dir", "")
        wave = weather.get("wave", 0)
        if "追い風" in wd and ws >= 5:
            if c == 1: s3 -= 2.5
            if c == 2: s3 += 1.5
        elif "追い風" in wd and 3 <= ws <= 4:
            if c == 1: s3 -= 1.0
            if c == 3: s3 += 0.5
        elif "向かい風" in wd and ws >= 5:
            if c == 1: s3 -= 2.5
            if c == 4: s3 += 1.5
        if wave >= 8 and c == 1:
            s3 -= 3.0; notes.append("高波警戒")
        sc["風速波高"] = s3

        # ④ モーター
        mr = r.get("motor_2ren", 33)
        s4 = 3.0 if mr > 50 else 1.5 if mr >= 40 else 0.5 if mr >= 30 else -2.0 if mr < 25 else 0
        if is_day1: s4 *= 0.5; notes.append("初日Mo0.5倍")
        sc["モーター"] = s4

        # ⑤ 展示タイム
        s5 = 0
        if c in ex_rank:
            rk = ex_rank[c]
            if rk == 1 and len(ex_sorted) > 1:
                diff = ex_sorted[1][1] - ex_sorted[0][1]
                s5 = 2.0 if diff >= 0.07 else 1.0 if diff >= 0.04 else 0
            elif rk == 2 and len(ex_sorted) > 2:
                diff = ex_sorted[2][1] - exhibition_times[c]
                s5 = 1.0 if diff >= 0.04 else 0
            if rk == 6:
                s5 = -3.0 if c == 1 else -2.0
                if c == 1: notes.append("⚠イン崩壊フラグ")
        sc["展示タイム"] = s5

        # ⑥ 平均ST
        st_val = r.get("avg_st", 0.15)
        sc["平均ST"] = 2.0 if st_val <= 0.10 else 1.0 if st_val <= 0.13 else -2.0 if st_val >= 0.20 else -1.0 if st_val >= 0.17 else 0

        # ⑦ Fペナ
        fc = r.get("f_count", 0)
        sc["Fペナ"] = -3.0 if fc >= 2 else (-2.0 if c >= 4 else -1.0) if fc == 1 else 0

        # ⑧ 選手力
        nr = r.get("national_rate", 5.0)
        s8 = 3.5 if nr >= 8 else 3.0 if nr >= 7.5 else 2.0 if nr >= 7 else 1.0 if nr >= 6 else 0 if nr >= 5 else -1.0 if nr >= 4 else -2.0
        if venue["rough"] and r.get("local_rate", 5.0) >= nr + 0.5:
            s8 += 1.0; notes.append("難水面適性+1")
        sc["選手力"] = s8

        # ⑨ 節間動態
        sc["節間動態"] = 0

        # ⑩ 進入変動
        sc["進入変動"] = 0

        # ⑪ クラス
        sc["クラス"] = {"A1": 2.5, "A2": 1.0, "B1": 0, "B2": -2.0}.get(r.get("class", "B1"), 0)

        # ⑫ 年齢
        age = r.get("age", 30)
        cr = r.get("class", "B1")
        s12 = 1.0 if 25 <= age <= 35 else 0.5 if 36 <= age <= 44 else 0 if 45 <= age <= 50 else -0.5 if age >= 51 else -0.5 if age <= 24 else 0
        if cr == "A1" and age >= 50 and s12 < 0:
            s12 = 0; notes.append("A1ベテラン補正")
        sc["年齢"] = s12

        # ⑬ コース別
        sc["コース別"] = 0

        # ⑭ 当地
        lr = r.get("local_rate", 5.0)
        s14 = 2.0 if lr >= nr + 1.0 else 1.0 if lr >= nr + 0.5 else -1.5 if lr <= nr - 1.0 else -0.5 if lr <= nr - 0.5 else 0
        if c == 1 and lr >= 6.5:
            s14 += 1.5; notes.append("当地6.5↑1C:+1.5")
        sc["当地"] = s14

        total = round(sum(sc.values()), 1)
        scored.append({**r, "scores": sc, "total": total, "notes": notes})

    return sorted(scored, key=lambda x: x["total"], reverse=True)


def generate_scenario(scored_racers, weather, venue_jcd):
    """展開シナリオと買い目をスコアに基づいて生成"""
    by_course = {r["course"]: r for r in scored_racers}
    # scored_racers はスコア降順ソート済み
    top = scored_racers[0]
    second = scored_racers[1] if len(scored_racers) > 1 else None
    third = scored_racers[2] if len(scored_racers) > 2 else None
    gap = round(top["total"] - second["total"], 1) if second else 99
    gap12 = round(second["total"] - third["total"], 1) if second and third else 99

    inner = by_course.get(1, {})

    # ── 決まり手予測 ──
    if top["course"] == 1:
        pat = "逃げ"
        sc_text = f"1C {inner.get('name','')} のイン逃げが本線。"
    elif top["course"] == 2:
        pat = "差し"
        sc_text = f"2C {top.get('name','')} の差し展開。1号艇の2着残りに注目。"
    elif top["course"] == 3:
        pat = "まくり差し"
        sc_text = f"3C {top.get('name','')} のまくり差し展開。"
    elif top["course"] in (4, 5, 6):
        pat = "まくり"
        sc_text = f"{top['course']}C {top.get('name','')} の外からのまくり。荒れ模様。"
    else:
        pat = "混戦"; sc_text = "展開が読みにくい混戦模様。"

    ws = weather.get("wind_speed", 0)
    wd = weather.get("wind_dir", "")
    if ws >= 5:
        sc_text += f" {wd}{ws}mの影響大。"
    if weather.get("wave", 0) >= 8:
        sc_text += " 高波注意。"

    # ── 1着想定率 ──
    if gap >= 4:   first_rate, conf = 0.60, "高"
    elif gap >= 2: first_rate, conf = 0.45, "中"
    elif gap >= 1: first_rate, conf = 0.33, "低"
    else:          first_rate, conf = 0.25, "極低"

    # ── スコアベースの着順配分率を算出 ──
    # 全6艇のスコアを使って相対的な強さを配分
    totals = [r["total"] for r in scored_racers]
    min_t = min(totals)
    # 全艇を正の値に補正（最低0.5）
    adjusted = [max(t - min_t + 0.5, 0.5) for t in totals]
    sum_adj = sum(adjusted)

    # 各艇の相対強度（1着候補としての比率）
    strength = [a / sum_adj for a in adjusted]

    # ── 2着候補率を展開パターン + スコアのハイブリッドで算出 ──
    # パターンベースの2着率（ベース値）
    pattern_2nd = {}
    if pat == "逃げ":
        pattern_2nd = {2: 0.343, 3: 0.271, 4: 0.15, 5: 0.10, 6: 0.05}
        # 1C以外が2着に来る確率をスコアで補正
    elif pat == "差し":
        pattern_2nd = {1: 0.60, 3: 0.15, 4: 0.10}
    elif pat == "まくり差し":
        pattern_2nd = {1: 0.55, 2: 0.15, 4: 0.10}
    elif pat == "まくり":
        outer = min(top["course"] + 1, 6)
        pattern_2nd = {1: 0.30, outer: 0.40}
        # 残りのコースにも少し配分
        for c in range(1, 7):
            if c != top["course"] and c not in pattern_2nd:
                pattern_2nd[c] = 0.05

    # スコア順位で補正: 上位の艇はパターン率を1.3倍、下位は0.7倍
    second_rates = {}
    for r in scored_racers:
        c = r["course"]
        if c == top["course"]:
            continue
        base = pattern_2nd.get(c, 0.05)
        # スコア順位での補正
        score_rank = scored_racers.index(r)
        if score_rank <= 1:   mult = 1.3  # スコア2位
        elif score_rank <= 2: mult = 1.1  # スコア3位
        elif score_rank >= 4: mult = 0.6  # スコア5-6位
        else:                 mult = 0.9
        second_rates[c] = round(base * mult, 4)

    # 正規化
    sr_sum = sum(second_rates.values())
    if sr_sum > 0:
        second_rates = {k: round(v / sr_sum, 4) for k, v in second_rates.items()}

    # ── 3着候補率（残り艇のスコア比率） ──
    def third_rate(first_c, second_c, third_c):
        """3着の想定率をスコアベースで算出"""
        remaining = [r for r in scored_racers if r["course"] not in (first_c, second_c)]
        if not remaining:
            return 0.25
        rem_scores = [max(r["total"] - min_t + 0.5, 0.5) for r in remaining]
        total_rem = sum(rem_scores)
        for i, r in enumerate(remaining):
            if r["course"] == third_c:
                return round(rem_scores[i] / total_rem, 4) if total_rem > 0 else 0.25
        return 0.1

    # ── 推奨判定 ──
    if gap < 1.0:
        rtype = "見送り"
        reason = f"スコア差 {gap}pt → 完全混戦のため見送り推奨"
        fms, btype = [], ""
    elif gap < 2.0:
        rtype = "注意"
        reason = f"スコア差 {gap}pt → 混戦気味。穴目検討"
        # 穴型: スコア上位2艇を1着候補にして広く
        c1 = top["course"]
        c2 = scored_racers[1]["course"]
        fms = [f"{c1}-{c2}-全", f"{c2}-{c1}-全"]
        btype = "3連単(穴型)"
    else:
        rtype = "買い"
        reason = f"スコア差 {gap}pt → {top.get('name','')}({top['course']}C)が有力"
        c1 = top["course"]
        # 2着候補上位2つ
        top2_seconds = sorted(second_rates.items(), key=lambda x: x[1], reverse=True)[:2]
        s_labels = [str(s[0]) for s in top2_seconds]
        fms = [f"{c1}-{'/'.join(s_labels)}-全"]

        # 2着候補が拮抗していたら展開型フォーメーション追加
        if len(top2_seconds) >= 2 and top2_seconds[0][1] - top2_seconds[1][1] < 0.1:
            fms.append(f"{c1}-{s_labels[1]}/{s_labels[0]}-全")
        btype = "3連単(基本型)" if gap >= 4 else "3連単(標準型)"

    # ── 全買い目を生成（スコアベース） ──
    bets = []
    if rtype != "見送り":
        first_c = top["course"]

        # 1着候補: スコア1位 (メイン) + スコア2位 (穴)
        first_candidates = [(first_c, first_rate)]
        if rtype == "注意":
            # 混戦時はスコア2位も1着候補に
            first_candidates.append((scored_racers[1]["course"], 1.0 - first_rate))

        for fc, f_rate in first_candidates:
            # 2着候補: fc以外で2着率が高い順に最大4艇
            s2_candidates = []
            for r in scored_racers:
                if r["course"] != fc:
                    s2r = second_rates.get(r["course"], 0.05)
                    # 1着候補がスコア1位でない場合、元の1位を2着に高めに設定
                    if fc != first_c and r["course"] == first_c:
                        s2r = max(s2r, 0.35)
                    s2_candidates.append((r["course"], s2r))
            s2_candidates = sorted(s2_candidates, key=lambda x: x[1], reverse=True)[:3]

            for s2c, s2r in s2_candidates:
                # 3着候補: 1着2着以外でスコア上位3艇
                remaining = [r for r in scored_racers if r["course"] not in (fc, s2c)]
                for t_r in remaining[:3]:
                    tc = t_r["course"]
                    t_rate = third_rate(fc, s2c, tc)
                    hit = round(f_rate * s2r * t_rate, 5)
                    if hit > 0.001:  # 的中率0.1%以上のみ
                        bets.append({
                            "bet": f"{fc}-{s2c}-{tc}",
                            "hit_rate": hit,
                            "req_odds": round(1.0 / hit, 1) if hit > 0 else 999,
                            "note": _classify_bet(hit, fc == first_c),
                        })

    # 重複除去 + 的中率降順ソート → 上位12件
    seen_bets = set()
    unique_bets = []
    for b in sorted(bets, key=lambda x: x["hit_rate"], reverse=True):
        if b["bet"] not in seen_bets:
            seen_bets.add(b["bet"])
            unique_bets.append(b)
    bets = unique_bets[:12]

    return {
        "scenario": sc_text, "pattern": pat, "rec_type": rtype,
        "rec_reason": reason, "formations": fms, "bet_type": btype,
        "bets": bets, "score_gap": gap, "confidence": conf,
    }


def _classify_bet(hit_rate: float, is_main_first: bool) -> str:
    """買い目を分類"""
    if hit_rate >= 0.08:
        return "◎本命"
    elif hit_rate >= 0.04:
        return "○対抗" if is_main_first else "▲穴"
    elif hit_rate >= 0.02:
        return "▲連下" if is_main_first else "△穴"
    else:
        return "△押さえ"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 表示ヘルパー
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def badge_html(c: int) -> str:
    css = COURSE_COLORS_CSS.get(c, "background:#888;color:#FFF;")
    return (f'<span style="display:inline-flex;align-items:center;justify-content:center;'
            f'width:30px;height:30px;border-radius:5px;font-weight:900;font-size:15px;'
            f'{css}">{c}</span>')


def bar_html(score: float) -> str:
    rng = 62  # 36 - (-26)
    pct = max(0, min(100, (score + 26) / rng * 100))
    zp = 26 / rng * 100
    clr = "#E8212A" if score >= 20 else "#F5C518" if score >= 12 else "#1B6DB5" if score >= 5 else "#888"
    left = zp if score >= 0 else pct
    w = abs(pct - zp)
    return (f'<div style="height:20px;background:#1a1a2e;border-radius:10px;'
            f'position:relative;overflow:hidden">'
            f'<div style="height:16px;border-radius:8px;margin-top:2px;'
            f'margin-left:{left}%;width:{w}%;'
            f'background:linear-gradient(90deg,{clr}CC,{clr})"></div>'
            f'<span style="position:absolute;right:8px;top:0;line-height:20px;'
            f'font-size:12px;font-weight:800;color:#FFF;'
            f'text-shadow:0 1px 3px rgba(0,0,0,0.8)">{score:.1f}</span></div>')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# メインUI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    st.set_page_config(page_title="🚤 ボートレース予想AI v3", page_icon="🚤",
                       layout="wide", initial_sidebar_state="collapsed")

    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap');
    .stApp { background:linear-gradient(135deg,#0a0a1a,#0d1b2a 40%,#1b2838);
             font-family:'Noto Sans JP',sans-serif; }
    .hdr { background:linear-gradient(90deg,#E8212A,#B71C1C); padding:16px 24px;
           border-radius:12px; display:flex; align-items:center; gap:14px;
           box-shadow:0 4px 20px rgba(232,33,42,0.35); margin-bottom:16px; }
    .hdr h1 { color:#FFF!important; font-size:22px!important; font-weight:900!important;
              letter-spacing:3px; margin:0!important; padding:0!important; }
    .hdr .sub { color:#ffcdd2; font-size:11px; letter-spacing:1px; }
    .card { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.07);
            border-radius:12px; padding:16px; margin-bottom:12px; }
    .sl { font-size:12px; font-weight:700; color:#E8212A; letter-spacing:2px; margin-bottom:8px; }
    div[data-testid="stMetric"] { background:rgba(255,255,255,0.04);
        border:1px solid rgba(255,255,255,0.07); border-radius:10px; padding:12px; }
    </style>""", unsafe_allow_html=True)

    st.markdown("""<div class="hdr"><span style="font-size:32px">🚤</span>
    <div><h1>BOAT RACE AI</h1><div class="sub">v3 SCORING SYSTEM ─ 14項目解析</div></div></div>""",
                unsafe_allow_html=True)

    # ── STEP 1 ──
    st.markdown('<div class="card"><div class="sl">STEP 1 ─ 開催日を選択</div>', unsafe_allow_html=True)
    sel_date = st.date_input("日付", value=date.today(), label_visibility="collapsed")
    date_str = sel_date.strftime("%Y-%m-%d")
    is_past = sel_date < date.today()
    st.markdown('</div>', unsafe_allow_html=True)

    # ── STEP 2 ──
    st.markdown('<div class="card"><div class="sl">STEP 2 ─ 開催場を選択</div>', unsafe_allow_html=True)
    with st.spinner("🔍 開催場を検索中..."):
        venues = get_active_venues(date_str)
    if not venues:
        st.warning(f"⚠️ {sel_date.strftime('%Y年%m月%d日')} の開催情報が見つかりません。")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    st.success(f"📍 {len(venues)}場が開催中")
    ncols = min(len(venues), 4)
    cols = st.columns(ncols)
    for i, v in enumerate(venues):
        with cols[i % ncols]:
            adj = f" 🟢+{v['in_adj']}" if v["in_adj"] > 0 else f" 🟠{v['in_adj']}" if v["in_adj"] < 0 else ""
            if st.button(f"🏟️ {v['name']}{adj}", key=f"v{v['jcd']}", use_container_width=True):
                st.session_state["venue"] = v["jcd"]
                st.session_state.pop("race", None)
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    sel_v = st.session_state.get("venue")
    if not sel_v:
        return
    vi = VENUES[sel_v]

    # ── STEP 3: レース (1→12 順, 発走時刻付き) ──
    st.markdown(f'<div class="card"><div class="sl">STEP 3 ─ {vi["name"]} レースを選択</div>',
                unsafe_allow_html=True)
    rtimes = get_race_times(sel_v, date_str)

    # 1行目 1R-6R, 2行目 7R-12R （順番固定）
    r1 = st.columns(6)
    for i in range(6):
        rno = i + 1
        with r1[i]:
            t = rtimes.get(rno, "")
            lbl = f"{rno}R\n{t}" if t else f"{rno}R"
            if st.button(lbl, key=f"r{rno}", use_container_width=True):
                st.session_state["race"] = rno
                st.rerun()
    r2 = st.columns(6)
    for i in range(6):
        rno = i + 7
        with r2[i]:
            t = rtimes.get(rno, "")
            prefix = "🏆" if rno == 12 else ""
            lbl = f"{prefix}{rno}R\n{t}" if t else f"{prefix}{rno}R"
            if st.button(lbl, key=f"r{rno}", use_container_width=True):
                st.session_state["race"] = rno
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    sel_r = st.session_state.get("race")
    if not sel_r:
        return

    # ━━━ 解析実行 ━━━
    st.divider()
    st.subheader(f"🏁 {vi['name']} {sel_r}R 解析")

    with st.spinner("📊 データ取得 & スコアリング中..."):
        racers = get_race_card(sel_v, date_str, sel_r)
        before = get_before_info(sel_v, date_str, sel_r)
        rr = get_race_result(sel_v, date_str, sel_r) if is_past else None

    if not racers:
        st.error("❌ 出走表データを取得できませんでした。")
        return

    scored = calc_scores(racers, sel_v, before.get("weather", {}),
                         before.get("exhibition_times", {}),
                         is_day1=False, is_final=(sel_r == 12))
    analysis = generate_scenario(scored, before.get("weather", {}), sel_v)

    # ── 天候 ──
    w = before.get("weather", {})
    wp = []
    if w.get("wind_dir"):   wp.append(w["wind_dir"])
    if w.get("wind_speed"): wp.append(f"{w['wind_speed']}m")
    if w.get("wave"):       wp.append(f"波高{w['wave']}cm")
    if wp:
        st.info(f"🌊 気象: {' / '.join(wp)}")

    # ── 過去レース結果 ──
    if is_past and rr and rr.get("has_result"):
        st.markdown("#### 📋 レース結果")
        if rr.get("order"):
            for o in rr["order"]:
                emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(o["rank"], "▪️")
                frame_badge = badge_html(o["frame"]) if o.get("frame") and 1 <= o["frame"] <= 6 else ""
                st.markdown(f'{emoji} **{o["rank"]}着** {frame_badge} {o.get("name","")}',
                            unsafe_allow_html=True)
        else:
            st.caption("着順データを取得できませんでした")

        if rr.get("payouts"):
            st.markdown("#### 💰 払戻金")
            pdf = pd.DataFrame([{
                "券種": p["type"],
                "組合せ": p["combo"],
                "払戻金": f"¥{p['amount']:,}",
            } for p in rr["payouts"]])
            st.dataframe(pdf, use_container_width=True, hide_index=True)
        else:
            st.caption("💰 払戻金データを取得できませんでした。"
                       "[公式結果ページ](https://www.boatrace.jp/owpc/pc/race/raceresult?"
                       f"rno={sel_r}&jcd={sel_v}&hd={date_str.replace('-','')})で確認できます。")
        st.divider()
    elif is_past:
        st.info("このレースの結果はまだ公開されていません。")

    # ── スコア一覧 ──
    st.markdown("#### 📊 全艇スコア一覧")
    for idx, r in enumerate(scored):
        crown = "👑 " if idx == 0 else ""
        bg = "rgba(245,197,24,0.06)" if idx == 0 else "transparent"
        nc = "#F5C518" if idx == 0 else "#ddd"
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;'
            f'background:{bg};border-radius:8px;margin-bottom:4px">'
            f'{badge_html(r["course"])}'
            f'<div style="min-width:80px;font-weight:700;font-size:14px;color:{nc}">'
            f'{crown}{r.get("name","")}</div>'
            f'<div style="min-width:60px;font-size:11px;color:#888">'
            f'{r.get("class","")}/{r.get("national_rate",0)}</div>'
            f'<div style="flex:1">{bar_html(r["total"])}</div></div>',
            unsafe_allow_html=True)

    with st.expander("📋 スコア内訳を表示"):
        rows = []
        for r in scored:
            row = {"コース": f'{r["course"]}C', "選手": r.get("name", ""), "合計": r["total"]}
            row.update(r["scores"])
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        for r in scored:
            if r.get("notes"):
                st.caption(f'**{r["course"]}C {r.get("name","")}**: {" / ".join(r["notes"])}')

    # ── 展開シナリオ ──
    st.markdown("#### 🌊 展開シナリオ")
    st.write(analysis["scenario"])

    # スコア上位3艇の展開補足
    top3 = scored[:3]
    detail_parts = []
    for i, r in enumerate(top3):
        rank_label = ["本命", "対抗", "3番手"][i]
        detail_parts.append(
            f"**{rank_label}**: {r['course']}C {r.get('name','')} "
            f"({r.get('class','')}, 勝率{r.get('national_rate',0)}) "
            f"スコア{r['total']}"
        )
    st.write(" / ".join(detail_parts))
    c1, c2 = st.columns(2)
    with c1: st.metric("決まり手予測", analysis["pattern"])
    with c2: st.metric("信頼度", analysis["confidence"])

    # ── 推奨判定 (修正3: Streamlitネイティブ表示) ──
    st.markdown("#### 🎯 推奨判定")
    rt = analysis["rec_type"]
    if rt == "見送り":
        st.warning(f"⚠️ **{rt}**\n\n{analysis['rec_reason']}")
    elif rt == "注意":
        st.info(f"⚡ **{rt}**\n\n{analysis['rec_reason']}")
    else:
        st.success(f"🎯 **{rt}**\n\n{analysis['rec_reason']}")

    if analysis.get("formations"):
        st.write(f"**{analysis.get('bet_type', 'フォーメーション')}:**")
        fcols = st.columns(len(analysis["formations"]))
        for i, fm in enumerate(analysis["formations"]):
            with fcols[i]:
                st.code(fm, language=None)

    # ── 期待値買い目 ──
    if analysis.get("bets"):
        st.markdown("#### 💰 期待値判定（買い目候補）")

        # スコア順位表示
        rank_str = " > ".join([f"{r['course']}C{r.get('name','')}" for r in scored[:3]])
        st.caption(f"📊 スコア順: {rank_str}")

        bet_data = []
        for b in analysis["bets"]:
            bet_data.append({
                "分類": b["note"],
                "買い目": b["bet"],
                "的中率": f'{b["hit_rate"]*100:.2f}%',
                "必要倍率": f'{b["req_odds"]:.1f}倍以上',
            })
        st.dataframe(pd.DataFrame(bet_data), use_container_width=True, hide_index=True)

        st.caption(
            "💡 **期待値** = 想定的中率 × 実オッズ → 1.0以上なら購入推奨。\n"
            "実オッズが「必要倍率」以上であれば期待値1.0超です。\n"
            "◎本命 → ○対抗 → ▲連下/穴 → △押さえ の優先度で検討。"
        )

    st.markdown("---")
    st.caption(
        "※ AI予想は参考情報です。購入は自己判断・自己責任で。\n"
        "※ ⑬コース別成績は個別選手ページ未取得のため0扱い。\n"
        "※ 1日最大5レース / 1レース投資上限は日次予算の25%以内を推奨。"
    )


if __name__ == "__main__":
    main()
