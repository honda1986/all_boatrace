"""
🚤 ボートレース予想アプリ v3
━━━━━━━━━━━━━━━━━━━━━━━━
Streamlit ベースの競艇スコアリング予想システム
v3 スコアリング14項目対応

起動方法:
  pip install streamlit requests beautifulsoup4 lxml
  streamlit run boatrace_app.py
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, date, timedelta
import time
import json

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 定数定義
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

COURSE_COLORS = {
    1: ("#FFFFFF", "#000000", "1px solid #999"),
    2: ("#000000", "#FFFFFF", "none"),
    3: ("#E8212A", "#FFFFFF", "none"),
    4: ("#1B6DB5", "#FFFFFF", "none"),
    5: ("#F5C518", "#000000", "none"),
    6: ("#2D8C3C", "#FFFFFF", "none"),
}

# 全国コース別平均値
NATIONAL_AVG = {
    1: {"win1": 55, "ren2": 72, "ren3": 81},
    2: {"win1": 15, "ren2": 40, "ren3": 59},
    3: {"win1": 12, "ren2": 34, "ren3": 54},
    4: {"win1": 11, "ren2": 29, "ren3": 50},
    5: {"win1": 6,  "ren2": 18, "ren3": 37},
    6: {"win1": 2,  "ren2": 8,  "ren3": 22},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# スクレイピング関数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@st.cache_data(ttl=300)
def get_active_venues(date_str: str) -> list:
    """指定日に開催中の場を取得"""
    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={hd}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        active = []
        # raceindex リンクから jcd を抽出
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "raceindex" in href and f"hd={hd}" in href:
                m = re.search(r"jcd=(\d{2})", href)
                if m:
                    jcd = m.group(1)
                    if jcd in VENUES and jcd not in [v["jcd"] for v in active]:
                        active.append({
                            "jcd": jcd,
                            "name": VENUES[jcd]["name"],
                            "region": VENUES[jcd]["region"],
                            "in_adj": VENUES[jcd]["in_adj"],
                        })
        # 重複除去
        seen = set()
        unique = []
        for v in active:
            if v["jcd"] not in seen:
                seen.add(v["jcd"])
                unique.append(v)
        return unique
    except Exception as e:
        st.error(f"開催場の取得に失敗: {e}")
        return []


@st.cache_data(ttl=120)
def get_race_card(jcd: str, date_str: str, race_no: int) -> list:
    """出走表データを取得"""
    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_no}&jcd={jcd}&hd={hd}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        return parse_racelist(soup)
    except Exception as e:
        st.error(f"出走表の取得に失敗: {e}")
        return []


@st.cache_data(ttl=60)
def get_before_info(jcd: str, date_str: str, race_no: int) -> dict:
    """直前情報（展示タイム・天候）を取得"""
    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={race_no}&jcd={jcd}&hd={hd}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        return parse_beforeinfo(soup)
    except Exception as e:
        st.warning(f"直前情報の取得に失敗: {e}")
        return {"weather": {}, "exhibition_times": {}, "start_times": {}}


def parse_racelist(soup: BeautifulSoup) -> list:
    """出走表HTMLをパース"""
    racers = []
    # テーブルの各行（tbody内）を探索
    tables = soup.find_all("tbody")

    for course_num, tbody in enumerate(tables[:6], 1):
        racer = {"course": course_num}
        try:
            # テキスト全体を取得して解析
            all_text = tbody.get_text(separator="|", strip=True)
            cells = [t.strip() for t in all_text.split("|") if t.strip()]

            # 登録番号を探す（4桁数字）
            reg_num = None
            for c in cells:
                m = re.match(r'^(\d{4})$', c)
                if m:
                    reg_num = m.group(1)
                    break

            # 選手名（漢字2-4文字のパターン）
            name = ""
            for c in cells:
                if re.match(r'^[一-龥ぁ-んァ-ヴー]{2,4}$', c) or re.match(r'^[一-龥ぁ-んァ-ヴー]+\s*[一-龥ぁ-んァ-ヴー]+$', c):
                    if c not in ["東京", "大阪", "福岡", "愛知", "埼玉", "群馬", "静岡", "長崎"]:
                        name = c
                        break

            # 級別
            class_rank = "B1"
            for c in cells:
                if c in ["A1", "A2", "B1", "B2"]:
                    class_rank = c
                    break

            # 数値データを抽出
            numbers = re.findall(r'(\d+\.?\d*)', all_text)
            float_nums = [float(n) for n in numbers]

            # 年齢（20-70の範囲の整数）
            age = 30
            for n in float_nums:
                if 18 <= n <= 70 and n == int(n):
                    age = int(n)
                    break

            # 勝率を探す（3.00-9.99の範囲）- 全国勝率と当地勝率
            win_rates = [n for n in float_nums if 2.0 <= n <= 10.0 and n != int(n)]

            national_rate = win_rates[0] if len(win_rates) > 0 else 5.0
            local_rate = win_rates[1] if len(win_rates) > 1 else national_rate

            # モーター2連率（20-70%の範囲）
            motor_rates = [n for n in float_nums if 15.0 <= n <= 75.0]
            motor_2ren = 33.0
            for mr in motor_rates:
                if mr != age and mr != national_rate * 10 and mr != local_rate * 10:
                    motor_2ren = mr
                    break

            # F数
            f_count = 0
            if "F1" in all_text:
                f_count = 1
            if "F2" in all_text:
                f_count = 2

            # 平均ST
            st_times = [n for n in float_nums if 0.05 <= n <= 0.30]
            avg_st = st_times[0] if st_times else 0.15

            racer.update({
                "number": reg_num or "----",
                "name": name or f"選手{course_num}",
                "class": class_rank,
                "age": age,
                "national_rate": national_rate,
                "local_rate": local_rate,
                "motor_2ren": motor_2ren,
                "f_count": f_count,
                "avg_st": avg_st,
            })
        except Exception:
            racer.update({
                "number": "----",
                "name": f"選手{course_num}",
                "class": "B1",
                "age": 30,
                "national_rate": 5.0,
                "local_rate": 5.0,
                "motor_2ren": 33.0,
                "f_count": 0,
                "avg_st": 0.15,
            })

        racers.append(racer)

    # 6艇に満たない場合はダミーを追加
    while len(racers) < 6:
        c = len(racers) + 1
        racers.append({
            "course": c, "number": "----", "name": f"選手{c}",
            "class": "B1", "age": 30, "national_rate": 5.0,
            "local_rate": 5.0, "motor_2ren": 33.0, "f_count": 0, "avg_st": 0.15,
        })

    return racers


def parse_beforeinfo(soup: BeautifulSoup) -> dict:
    """直前情報HTMLをパース"""
    result = {
        "weather": {"wind_dir": "", "wind_speed": 0, "wave": 0, "weather": ""},
        "exhibition_times": {},
        "start_times": {},
    }
    try:
        text = soup.get_text(separator=" ", strip=True)

        # 風速
        wm = re.search(r'(\d+)\s*m', text)
        if wm:
            result["weather"]["wind_speed"] = int(wm.group(1))

        # 風向き
        if "追い風" in text or "追" in text:
            result["weather"]["wind_dir"] = "追い風"
        elif "向かい風" in text or "向" in text:
            result["weather"]["wind_dir"] = "向かい風"

        # 波高
        wave_m = re.search(r'波高\s*(\d+)\s*cm', text)
        if wave_m:
            result["weather"]["wave"] = int(wave_m.group(1))
        else:
            wave_m2 = re.search(r'(\d+)\s*cm', text)
            if wave_m2:
                result["weather"]["wave"] = int(wave_m2.group(1))

        # 展示タイム（6.XX のパターン）
        ex_times = re.findall(r'(\d\.\d{2})', text)
        for i, et in enumerate(ex_times[:6]):
            result["exhibition_times"][i + 1] = float(et)

    except Exception:
        pass

    return result


@st.cache_data(ttl=120)
def get_race_results_today(jcd: str, date_str: str) -> dict:
    """当日の既走レース結果を取得（節間成績用）"""
    hd = date_str.replace("-", "")
    results = {}
    # 簡易的に最初の数レースの結果を取得
    for rno in range(1, 13):
        url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={jcd}&hd={hd}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text()
            if "結果" not in text and "着" not in text:
                break
            results[rno] = text
        except Exception:
            break
        time.sleep(0.3)
    return results


@st.cache_data(ttl=300)
def get_race_result_detail(jcd: str, date_str: str, race_no: int) -> dict:
    """特定レースの着順結果と払い戻し金を取得"""
    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_no}&jcd={jcd}&hd={hd}"
    result = {"has_result": False, "order": [], "payouts": []}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)

        # レース結果が存在するか判定
        if "レース結果" not in text and "払戻金" not in text:
            return result

        result["has_result"] = True

        # ─── 着順の取得 ───
        # 結果テーブル(tbody)から着順を取得
        result_tables = soup.find_all("table", class_=re.compile(r"is-w495|tblResultAll"))
        if not result_tables:
            # 汎用: tbody を探して着順データを取得
            all_tbodies = soup.find_all("tbody")
            for tbody in all_tbodies:
                rows = tbody.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 3:
                        cell_texts = [c.get_text(strip=True) for c in cells]
                        # 着順パターン: 1着, 2着... or 1, 2, 3...
                        for i, ct in enumerate(cell_texts):
                            if ct in ["1", "2", "3", "4", "5", "6"]:
                                # 次のセルにコース番号がある可能性
                                if i + 1 < len(cell_texts):
                                    m = re.search(r'(\d)', cell_texts[i + 1])
                                    if m:
                                        result["order"].append({
                                            "rank": int(ct),
                                            "course": int(m.group(1)),
                                            "name": cell_texts[i + 2] if i + 2 < len(cell_texts) else "",
                                        })

        # テーブルからの取得がうまくいかない場合、テキストベースで着順抽出
        if not result["order"]:
            # パターン: 着 数字 選手名 / コース番号
            order_matches = re.findall(r'(\d)着.*?(\d)号艇', text)
            if order_matches:
                for rank_str, course_str in order_matches:
                    result["order"].append({
                        "rank": int(rank_str),
                        "course": int(course_str),
                        "name": "",
                    })

        # さらにフォールバック: "1-2-3" のような結果文字列
        if not result["order"]:
            combo_m = re.search(r'(\d)\s*[-ー]\s*(\d)\s*[-ー]\s*(\d)', text)
            if combo_m:
                for rank, crs in enumerate([combo_m.group(1), combo_m.group(2), combo_m.group(3)], 1):
                    result["order"].append({"rank": rank, "course": int(crs), "name": ""})

        # ─── 払い戻し金の取得 ───
        payout_patterns = [
            (r'3連単\s*(\d+[-ー]\d+[-ー]\d+)\s*[¥￥]?\s*([\d,]+)\s*円?', "3連単"),
            (r'3連複\s*(\d+[=＝]\d+[=＝]\d+)\s*[¥￥]?\s*([\d,]+)\s*円?', "3連複"),
            (r'2連単\s*(\d+[-ー]\d+)\s*[¥￥]?\s*([\d,]+)\s*円?', "2連単"),
            (r'2連複\s*(\d+[=＝]\d+)\s*[¥￥]?\s*([\d,]+)\s*円?', "2連複"),
            (r'拡連複\s*(\d+[=＝]\d+)\s*[¥￥]?\s*([\d,]+)\s*円?', "拡連複"),
            (r'単勝\s*(\d+)\s*[¥￥]?\s*([\d,]+)\s*円?', "単勝"),
            (r'複勝\s*(\d+)\s*[¥￥]?\s*([\d,]+)\s*円?', "複勝"),
        ]

        for pat, bet_type in payout_patterns:
            matches = re.findall(pat, text)
            for m in matches:
                combo = m[0]
                amount = int(m[1].replace(",", ""))
                result["payouts"].append({
                    "type": bet_type,
                    "combo": combo,
                    "amount": amount,
                })

        # 払戻テーブルからの別パターン取得
        if not result["payouts"]:
            # 金額パターンの集約取得
            payout_section = False
            lines = text.split()
            bet_types_order = ["3連単", "3連複", "2連単", "2連複", "拡連複", "単勝", "複勝"]

            for tbl in soup.find_all("table"):
                tbl_text = tbl.get_text(separator="|", strip=True)
                if any(bt in tbl_text for bt in ["3連単", "2連単", "単勝"]):
                    # 払戻テーブル発見
                    rows = tbl.find_all("tr")
                    for row in rows:
                        cells = row.find_all(["td", "th"])
                        cell_texts = [c.get_text(strip=True) for c in cells]
                        row_text = " ".join(cell_texts)
                        for bt in bet_types_order:
                            if bt in row_text:
                                # 組番を探す
                                combo_m = re.search(r'(\d+\s*[-ー=＝]\s*\d+(?:\s*[-ー=＝]\s*\d+)?)', row_text)
                                if not combo_m:
                                    combo_m = re.search(r'(\d+)', row_text.split(bt)[-1])
                                # 金額を探す
                                amounts = re.findall(r'([\d,]+)\s*円', row_text)
                                if not amounts:
                                    amounts = re.findall(r'¥\s*([\d,]+)', row_text)
                                if not amounts:
                                    # 純粋に大きな数字を探す
                                    nums = re.findall(r'([\d,]{3,})', row_text)
                                    amounts = [n for n in nums if int(n.replace(",", "")) >= 100]

                                if combo_m and amounts:
                                    combo_str = combo_m.group(1).replace(" ", "")
                                    for amt_str in amounts[:1]:
                                        amt = int(amt_str.replace(",", ""))
                                        if amt >= 100:
                                            result["payouts"].append({
                                                "type": bt,
                                                "combo": combo_str,
                                                "amount": amt,
                                            })
                                break

    except Exception as e:
        st.warning(f"レース結果の取得に失敗: {e}")

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# v3 スコアリングエンジン
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calc_scores(racers: list, venue_jcd: str, weather: dict,
                exhibition_times: dict, is_day1: bool = False,
                is_final: bool = False) -> list:
    """v3 14項目スコアリング"""
    venue = VENUES[venue_jcd]
    scored = []

    # 展示タイムのランク算出
    ex_sorted = sorted(exhibition_times.items(), key=lambda x: x[1]) if exhibition_times else []
    ex_rank = {}
    for rank, (course, _) in enumerate(ex_sorted, 1):
        ex_rank[course] = rank

    best_ex = ex_sorted[0][1] if ex_sorted else 0
    worst_ex = ex_sorted[-1][1] if ex_sorted else 0

    for r in racers:
        c = r["course"]
        scores = {}
        notes = []

        # ① コース基礎点
        base = {1: 7, 2: 5, 3: 4, 4: 3.5, 5: 3, 6: 1.5}
        s1 = base.get(c, 3)
        if is_final and c == 1:
            s1 = 12
            notes.append("優勝戦1C補正")
        scores["s01_コース基礎"] = s1

        # ② 場別イン補正（1Cのみ適用）
        s2 = venue["in_adj"] if c == 1 else 0
        scores["s02_場別イン"] = s2

        # ③ 風速・波高補正
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
            notes.append("追い風3-4m:まくり差し展開")
        elif "向かい風" in wd and ws >= 5:
            if c == 1: s3 -= 2.5
            if c == 4: s3 += 1.5
        if wave >= 8:
            if c == 1: s3 -= 3.0
            notes.append("高波警戒")
        scores["s03_風速波高"] = s3

        # ④ モーター2連率
        mr = r.get("motor_2ren", 33)
        if mr > 50:     s4 = 3.0
        elif mr >= 40:  s4 = 1.5
        elif mr >= 30:  s4 = 0.5
        elif mr < 25:   s4 = -2.0
        else:           s4 = 0
        if is_day1:
            s4 *= 0.5
            notes.append("初日モーター補正0.5倍")
        scores["s04_モーター"] = s4

        # ⑤ 展示タイム
        s5 = 0
        if ex_rank.get(c):
            rank = ex_rank[c]
            my_time = exhibition_times.get(c, 0)
            if rank == 1 and best_ex > 0 and len(ex_sorted) > 1:
                diff = ex_sorted[1][1] - best_ex
                if diff >= 0.07:
                    s5 = 2.0
                elif diff >= 0.04:
                    s5 = 1.0
            elif rank == 2 and len(ex_sorted) > 2:
                diff = ex_sorted[2][1] - my_time
                if diff >= 0.04:
                    s5 = 1.0
            if rank == 6:
                s5 = -2.0
                if c == 1:
                    s5 = -3.0
                    notes.append("⚠️イン崩壊フラグ:展示最下位1C")
        scores["s05_展示タイム"] = s5

        # ⑥ 平均ST
        avg_st = r.get("avg_st", 0.15)
        if avg_st <= 0.10:    s6 = 2.0
        elif avg_st >= 0.20:  s6 = -2.0
        elif avg_st <= 0.13:  s6 = 1.0
        elif avg_st >= 0.17:  s6 = -1.0
        else:                 s6 = 0
        scores["s06_平均ST"] = s6

        # ⑦ Fペナルティ
        fc = r.get("f_count", 0)
        if fc >= 2:     s7 = -3.0
        elif fc == 1:
            s7 = -2.0 if c >= 4 else -1.0  # ダッシュ/スロー推定
        else:           s7 = 0
        scores["s07_Fペナ"] = s7

        # ⑧ 選手力（勝率ベース）
        nr = r.get("national_rate", 5.0)
        if nr >= 8.0:    s8 = 3.5
        elif nr >= 7.5:  s8 = 3.0
        elif nr >= 7.0:  s8 = 2.0
        elif nr >= 6.0:  s8 = 1.0
        elif nr >= 5.0:  s8 = 0
        elif nr >= 4.0:  s8 = -1.0
        else:            s8 = -2.0
        # 難水面当地補正
        if venue["rough"] and r.get("local_rate", 5.0) >= nr + 0.5:
            s8 += 1.0
            notes.append("難水面適性+1.0")
        scores["s08_選手力"] = s8

        # ⑨ 節間順位動態（簡易版 - データ不足時は0）
        s9 = 0
        scores["s09_節間動態"] = s9

        # ⑩ 進入変動（デフォルト0）
        s10 = 0
        scores["s10_進入変動"] = s10

        # ⑪ 選手クラス補正
        cr = r.get("class", "B1")
        class_scores = {"A1": 2.5, "A2": 1.0, "B1": 0, "B2": -2.0}
        s11 = class_scores.get(cr, 0)
        scores["s11_クラス"] = s11

        # ⑫ 年齢補正
        age = r.get("age", 30)
        if 25 <= age <= 35:    s12 = 1.0
        elif 36 <= age <= 44:  s12 = 0.5
        elif 45 <= age <= 50:  s12 = 0
        elif age >= 51:        s12 = -0.5
        elif age <= 24:        s12 = -0.5
        else:                  s12 = 0
        # A1で50歳以上は年齢減算0
        if cr == "A1" and age >= 50 and s12 < 0:
            s12 = 0
            notes.append("A1ベテラン年齢補正免除")
        scores["s12_年齢"] = s12

        # ⑬ 全国コース別成績（詳細データ未取得時は0）
        s13 = 0
        notes.append("⑬コース別:データ未取得=0")
        scores["s13_コース別"] = s13

        # ⑭ 当地成績補正
        lr = r.get("local_rate", 5.0)
        s14 = 0
        if lr >= nr + 1.0:     s14 = 2.0
        elif lr >= nr + 0.5:   s14 = 1.0
        elif lr <= nr - 1.0:   s14 = -1.5
        elif lr <= nr - 0.5:   s14 = -0.5
        # 当地勝率6.5以上の1C選手
        if c == 1 and lr >= 6.5:
            s14 += 1.5
            notes.append("当地勝率6.5以上の1C:+1.5")
        scores["s14_当地"] = s14

        total = sum(scores.values())
        scored.append({
            **r,
            "scores": scores,
            "total": round(total, 1),
            "notes": notes,
        })

    return sorted(scored, key=lambda x: x["total"], reverse=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 展開シナリオ・買い目生成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_scenario(scored_racers: list, weather: dict, venue_jcd: str) -> dict:
    """展開シナリオと買い目を生成（スコアリングベース）"""
    venue = VENUES[venue_jcd]
    by_course = {r["course"]: r for r in scored_racers}
    # scored_racers はスコア降順
    top = scored_racers[0]
    second = scored_racers[1] if len(scored_racers) > 1 else None
    third = scored_racers[2] if len(scored_racers) > 2 else None
    score_gap = top["total"] - second["total"] if second else 99

    # 1Cの選手
    inner = by_course.get(1, {})

    # ─── 展開予測 ───
    if top["course"] == 1:
        pattern = "逃げ"
        scenario = f"1C {inner.get('name', '')}がスタート決めて逃げ切り濃厚。"
    elif top["course"] == 2:
        pattern = "差し"
        scenario = f"2C {top.get('name', '')}の差し展開。1号艇の2着残りに注目。"
    elif top["course"] == 3:
        pattern = "まくり差し"
        scenario = f"3C {top.get('name', '')}のまくり差し展開。"
    elif top["course"] in [4, 5, 6]:
        pattern = "まくり"
        scenario = f"{top['course']}C {top.get('name', '')}の外からのまくり展開。荒れるレース。"
    else:
        pattern = "混戦"
        scenario = "展開が読みにくい混戦模様。"

    # 風の影響を追加
    ws = weather.get("wind_speed", 0)
    wd = weather.get("wind_dir", "")
    if ws >= 5:
        scenario += f" {wd}{ws}mの影響大。"
    if weather.get("wave", 0) >= 8:
        scenario += " 高波注意。"

    # ─── 信頼度・1着想定率 ───
    if score_gap >= 4:
        first_rate = 0.60
        confidence = "高"
    elif score_gap >= 2:
        first_rate = 0.45
        confidence = "中"
    elif score_gap >= 1:
        first_rate = 0.33
        confidence = "低"
    else:
        first_rate = 0.25
        confidence = "極低"

    # ─── スコアベースで2着・3着候補を決定 ───
    # 1着候補 = スコア1位
    first_c = top["course"]

    # 2着候補: スコア上位からfirst_cを除いた上位3名 (展開パターンで重み付け)
    second_pool = [r for r in scored_racers if r["course"] != first_c]

    # 展開パターン別の2着補正: パターンに合致する艇はスコアにボーナス
    def second_sort_key(r):
        bonus = 0
        c = r["course"]
        if pattern == "逃げ":
            if c == 2: bonus = 3.0
            elif c == 3: bonus = 2.0
            elif c == 4: bonus = 1.0
        elif pattern == "差し":
            if c == 1: bonus = 4.0  # イン2着残り
            elif c == 3: bonus = 1.5
        elif pattern == "まくり差し":
            if c == 1: bonus = 3.5  # イン2着残り
            elif c == 2: bonus = 1.5
        elif pattern == "まくり":
            if c == first_c + 1 and c <= 6: bonus = 3.0  # まくり艇の外側
            elif c == 1: bonus = 2.0
        return r["total"] + bonus

    second_pool_sorted = sorted(second_pool, key=second_sort_key, reverse=True)
    second_candidates = second_pool_sorted[:3]  # 上位3名

    # 3着候補: 残り全艇からスコア上位
    # ─── 推奨判定 & 買い目生成 ───
    recommendation = {}
    bets = []

    if score_gap < 1.0:
        recommendation = {
            "type": "見送り",
            "reason": f"スコア差{score_gap:.1f}pt - 完全混戦のため見送り推奨",
            "confidence": confidence,
        }
        # 見送りでも参考買い目は出す
        top2 = scored_racers[:3]
        formations = []
        for i, a in enumerate(top2):
            for j, b in enumerate(top2):
                if i != j:
                    formations.append(f"{a['course']}-{b['course']}-全")
                    if len(formations) >= 4:
                        break
            if len(formations) >= 4:
                break
        recommendation["formations"] = formations
        recommendation["bet_type"] = "3連単フォーメーション(参考・広め)"

    elif score_gap < 2.0:
        recommendation = {
            "type": "注意",
            "reason": f"スコア差{score_gap:.1f}pt - 混戦。穴目を検討",
            "confidence": confidence,
        }
        sc1 = second_candidates[0]["course"] if second_candidates else 2
        sc2 = second_candidates[1]["course"] if len(second_candidates) > 1 else 3
        formations = [
            f"{first_c}-{sc1}-全",
            f"{first_c}-{sc2}-全",
            f"{sc1}-{first_c}-全",
        ]
        recommendation["formations"] = formations
        recommendation["bet_type"] = "3連単フォーメーション(穴型)"

    else:
        recommendation = {
            "type": "買い",
            "reason": f"スコア差{score_gap:.1f}pt - {top.get('name', '')}({first_c}C)が有力",
            "confidence": confidence,
        }
        sc1 = second_candidates[0]["course"] if second_candidates else 2
        sc2 = second_candidates[1]["course"] if len(second_candidates) > 1 else 3
        formations = [
            f"{first_c}-{sc1}/{sc2}-全",
        ]
        recommendation["formations"] = formations
        recommendation["bet_type"] = "3連単フォーメーション(基本型)"

    # ─── 具体的3連単買い目をスコアベースで生成 ───
    # 1着候補: スコア上位2名
    first_candidates = scored_racers[:2]
    # 本命軸 (スコア1位) の買い目
    for sc in second_candidates[:3]:
        sc_c = sc["course"]
        # 2着想定率: スコア差に応じた簡易算出
        sc_gap = top["total"] - sc["total"]
        if sc_gap <= 2:
            sec_rate = 0.30
        elif sc_gap <= 4:
            sec_rate = 0.25
        elif sc_gap <= 6:
            sec_rate = 0.20
        else:
            sec_rate = 0.12

        # 展開パターン一致ボーナス
        if pattern == "逃げ" and sc_c in [2, 3]:
            sec_rate *= 1.3
        elif pattern == "差し" and sc_c == 1:
            sec_rate *= 1.4
        elif pattern == "まくり差し" and sc_c == 1:
            sec_rate *= 1.3
        elif pattern == "まくり" and sc_c == first_c + 1:
            sec_rate *= 1.2

        # 3着候補
        third_pool = [r for r in scored_racers if r["course"] != first_c and r["course"] != sc_c]
        for tr in third_pool[:3]:
            tr_c = tr["course"]
            # 3着想定率
            tr_gap = top["total"] - tr["total"]
            if tr_gap <= 3:
                trd_rate = 0.30
            elif tr_gap <= 5:
                trd_rate = 0.25
            else:
                trd_rate = 0.15

            hit_rate = first_rate * sec_rate * trd_rate
            req_odds = 1.0 / hit_rate if hit_rate > 0 else 999
            bets.append({
                "bet": f"{first_c}-{sc_c}-{tr_c}",
                "hit_rate": round(hit_rate, 4),
                "req_odds": round(req_odds, 1),
                "note": "本命" if hit_rate >= 0.02 else "押さえ",
            })

    # 対抗軸 (スコア2位) の買い目 - スコア差4pt未満の混戦時
    if score_gap < 4 and second:
        alt_first = second["course"]
        alt_second_pool = [r for r in scored_racers if r["course"] != alt_first][:3]
        for sc in alt_second_pool[:2]:
            sc_c = sc["course"]
            third_pool = [r for r in scored_racers if r["course"] != alt_first and r["course"] != sc_c]
            for tr in third_pool[:2]:
                tr_c = tr["course"]
                hit_rate = (1 - first_rate) * 0.35 * 0.25
                req_odds = 1.0 / hit_rate if hit_rate > 0 else 999
                bets.append({
                    "bet": f"{alt_first}-{sc_c}-{tr_c}",
                    "hit_rate": round(hit_rate, 4),
                    "req_odds": round(req_odds, 1),
                    "note": "穴",
                })

    # 重複除去 & 的中率上位に絞る
    seen_bets = set()
    unique_bets = []
    for b in bets:
        if b["bet"] not in seen_bets:
            seen_bets.add(b["bet"])
            unique_bets.append(b)
    bets = sorted(unique_bets, key=lambda x: x["hit_rate"], reverse=True)[:10]

    return {
        "scenario": scenario,
        "pattern": pattern,
        "recommendation": recommendation,
        "bets": bets,
        "score_gap": score_gap,
        "confidence": confidence,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Streamlit UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def apply_custom_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap');

    .stApp {
        background: linear-gradient(135deg, #0a0a1a 0%, #0d1b2a 40%, #1b2838 100%);
        font-family: 'Noto Sans JP', sans-serif;
    }

    /* ヘッダー */
    .app-header {
        background: linear-gradient(90deg, #E8212A, #B71C1C);
        padding: 18px 24px;
        border-radius: 12px;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 14px;
        box-shadow: 0 4px 24px rgba(232,33,42,0.35);
    }
    .app-header h1 {
        color: white !important;
        font-size: 22px !important;
        font-weight: 900 !important;
        letter-spacing: 3px;
        margin: 0 !important;
        padding: 0 !important;
    }
    .app-header .sub {
        color: #ffcdd2;
        font-size: 11px;
        letter-spacing: 1px;
    }

    /* カード */
    .card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 14px;
    }
    .card-title {
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 2px;
        margin-bottom: 10px;
    }

    /* コースバッジ */
    .course-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 30px;
        height: 30px;
        border-radius: 5px;
        font-weight: 900;
        font-size: 15px;
        margin-right: 8px;
        flex-shrink: 0;
    }

    /* スコアバー */
    .score-bar-bg {
        height: 20px;
        background: #1a1a2e;
        border-radius: 10px;
        position: relative;
        overflow: hidden;
        width: 100%;
    }
    .score-bar-fill {
        height: 16px;
        border-radius: 8px;
        margin-top: 2px;
        transition: width 0.6s ease;
    }
    .score-label {
        position: absolute;
        right: 8px;
        top: 0;
        line-height: 20px;
        font-size: 12px;
        font-weight: 800;
        color: white;
        text-shadow: 0 1px 3px rgba(0,0,0,0.8);
    }

    /* ボタン */
    .venue-btn {
        display: inline-block;
        padding: 8px 16px;
        border-radius: 8px;
        border: 1px solid rgba(255,255,255,0.12);
        background: rgba(255,255,255,0.05);
        color: #bbb;
        font-size: 14px;
        cursor: pointer;
        margin: 3px;
        text-align: center;
        transition: all 0.2s;
    }
    .venue-btn:hover {
        background: rgba(232,33,42,0.15);
        border-color: #E8212A;
        color: white;
    }
    .venue-btn.active {
        background: rgba(232,33,42,0.25);
        border: 2px solid #E8212A;
        color: white;
        font-weight: 700;
    }

    /* 推奨ラベル */
    .rec-buy {
        background: rgba(76,175,80,0.1);
        border: 1px solid rgba(76,175,80,0.3);
        border-radius: 10px;
        padding: 14px;
    }
    .rec-skip {
        background: rgba(255,152,0,0.1);
        border: 1px solid rgba(255,152,0,0.3);
        border-radius: 10px;
        padding: 14px;
    }
    .rec-caution {
        background: rgba(255,235,59,0.08);
        border: 1px solid rgba(255,235,59,0.25);
        border-radius: 10px;
        padding: 14px;
    }

    /* フォーメーション */
    .formation-chip {
        display: inline-block;
        padding: 5px 14px;
        background: rgba(76,175,80,0.15);
        border-radius: 6px;
        font-size: 14px;
        font-weight: 700;
        color: #4CAF50;
        font-family: monospace;
        margin: 3px;
    }

    /* テーブル調整 */
    .stDataFrame { font-size: 12px; }

    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 10px;
        padding: 12px;
    }
    </style>
    """, unsafe_allow_html=True)


def render_header():
    st.markdown("""
    <div class="app-header">
        <span style="font-size:32px">🚤</span>
        <div>
            <h1>BOAT RACE AI</h1>
            <div class="sub">v3 SCORING SYSTEM ─ 14項目解析</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_course_badge(course: int) -> str:
    bg, fg, border = COURSE_COLORS[course]
    border_style = f"border:{border};" if border != "none" else ""
    return f'<span class="course-badge" style="background:{bg};color:{fg};{border_style}">{course}</span>'


def render_score_bar(score: float, max_s=36, min_s=-26) -> str:
    rng = max_s - min_s
    pct = max(0, min(100, (score - min_s) / rng * 100))
    zero_pct = (0 - min_s) / rng * 100

    if score >= 20:   color = "#E8212A"
    elif score >= 12: color = "#F5C518"
    elif score >= 5:  color = "#1B6DB5"
    else:             color = "#888"

    if score >= 0:
        left = zero_pct
        width = pct - zero_pct
    else:
        left = pct
        width = zero_pct - pct

    return f"""
    <div class="score-bar-bg">
        <div class="score-bar-fill" style="margin-left:{left}%;width:{width}%;background:linear-gradient(90deg,{color}CC,{color})"></div>
        <span class="score-label">{score:.1f}</span>
    </div>
    """


def main():
    st.set_page_config(
        page_title="🚤 ボートレース予想AI v3",
        page_icon="🚤",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    apply_custom_css()
    render_header()

    # ─── STEP 1: 日付選択 ───
    st.markdown('<div class="card"><div class="card-title" style="color:#E8212A">STEP 1 ─ 開催日を選択</div>', unsafe_allow_html=True)
    col1, col2 = st.columns([2, 3])
    with col1:
        selected_date = st.date_input(
            "開催日",
            value=date.today(),
            label_visibility="collapsed",
        )
    date_str = selected_date.strftime("%Y-%m-%d")
    st.markdown('</div>', unsafe_allow_html=True)

    # ─── STEP 2: 開催場検索 ───
    st.markdown('<div class="card"><div class="card-title" style="color:#E8212A">STEP 2 ─ 開催場を選択</div>', unsafe_allow_html=True)

    with st.spinner("🔍 開催場を検索中..."):
        active_venues = get_active_venues(date_str)

    if not active_venues:
        st.warning(f"⚠️ {selected_date.strftime('%Y年%m月%d日')} の開催情報が見つかりません。日付を確認してください。")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    st.success(f"📍 {len(active_venues)}場が開催中")

    # 地域別にグループ化
    regions = {}
    for v in active_venues:
        reg = v["region"]
        if reg not in regions:
            regions[reg] = []
        regions[reg].append(v)

    venue_options = {f"{v['name']} ({v['jcd']})": v["jcd"] for v in active_venues}
    venue_names = list(venue_options.keys())

    # 場の表示
    cols = st.columns(min(len(active_venues), 4))
    selected_venue_jcd = st.session_state.get("selected_venue", None)

    for i, v in enumerate(active_venues):
        with cols[i % len(cols)]:
            adj_str = ""
            if v["in_adj"] > 0:
                adj_str = f" 🟢+{v['in_adj']}"
            elif v["in_adj"] < 0:
                adj_str = f" 🟠{v['in_adj']}"

            if st.button(
                f"🏟️ {v['name']}{adj_str}",
                key=f"venue_{v['jcd']}",
                use_container_width=True,
            ):
                st.session_state["selected_venue"] = v["jcd"]
                st.session_state["selected_race"] = None
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    selected_venue_jcd = st.session_state.get("selected_venue", None)
    if not selected_venue_jcd:
        return

    venue_info = VENUES[selected_venue_jcd]

    # ─── STEP 3: レース選択 ───
    st.markdown(f"""
    <div class="card">
        <div class="card-title" style="color:#E8212A">
            STEP 3 ─ {venue_info['name']} レースを選択
        </div>
    """, unsafe_allow_html=True)

    race_cols = st.columns(6)
    for i in range(12):
        r = i + 1
        with race_cols[i % 6]:
            label = f"{r}R"
            if r == 12:
                label = f"🏆{r}R"
            if st.button(label, key=f"race_{r}", use_container_width=True):
                st.session_state["selected_race"] = r
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    selected_race = st.session_state.get("selected_race", None)
    if not selected_race:
        return

    # ─── 解析実行 ───
    st.markdown(f"""
    <div class="card" style="border-color:rgba(232,33,42,0.3)">
        <div style="text-align:center;font-size:15px;font-weight:800;color:#E8212A;letter-spacing:2px">
            🏁 {venue_info['name']} {selected_race}R 解析中...
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("📊 データ取得 & スコアリング中..."):
        # データ取得
        racers = get_race_card(selected_venue_jcd, date_str, selected_race)
        before = get_before_info(selected_venue_jcd, date_str, selected_race)

        if not racers:
            st.error("❌ 出走表データを取得できませんでした。レースがまだ確定していない可能性があります。")
            return

        # スコアリング実行
        is_final = (selected_race == 12)
        scored = calc_scores(
            racers,
            selected_venue_jcd,
            before.get("weather", {}),
            before.get("exhibition_times", {}),
            is_day1=False,
            is_final=is_final,
        )

        # 展開・買い目生成
        analysis = generate_scenario(scored, before.get("weather", {}), selected_venue_jcd)

    # ─── 結果表示 ───
    st.markdown(f"""
    <div class="app-header" style="background:linear-gradient(90deg,#1B6DB5,#0D47A1)">
        <span style="font-size:28px">🏁</span>
        <div>
            <h1 style="font-size:18px!important">{venue_info['name']} {selected_race}R 解析結果</h1>
            <div class="sub">v3スコアリング14項目</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 天候情報
    w = before.get("weather", {})
    weather_str = ""
    if w.get("wind_dir"):
        weather_str += f"{w['wind_dir']} "
    if w.get("wind_speed"):
        weather_str += f"{w['wind_speed']}m "
    if w.get("wave"):
        weather_str += f"/ 波高{w['wave']}cm"

    if weather_str:
        st.info(f"🌊 気象: {weather_str}")

    # スコア一覧
    st.markdown("""
    <div class="card">
        <div class="card-title" style="color:#F5C518">📊 全艇スコア一覧（①〜⑭合計）</div>
    </div>
    """, unsafe_allow_html=True)

    for idx, r in enumerate(scored):
        crown = "👑 " if idx == 0 else ""
        badge = render_course_badge(r["course"])
        bar = render_score_bar(r["total"])

        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;padding:6px 10px;
                     background:{'rgba(245,197,24,0.06)' if idx==0 else 'transparent'};
                     border-radius:8px">
            {badge}
            <div style="min-width:70px;font-weight:700;font-size:14px;
                        color:{'#F5C518' if idx==0 else '#ddd'}">{crown}{r.get('name','')}</div>
            <div style="min-width:55px;font-size:11px;color:#888">{r.get('class','')}/{r.get('national_rate',0)}</div>
            <div style="flex:1">{bar}</div>
        </div>
        """, unsafe_allow_html=True)

    # スコア内訳（展開可能）
    with st.expander("📋 スコア内訳を表示"):
        import pandas as pd
        rows = []
        for r in scored:
            row = {"コース": f"{r['course']}C", "選手": r.get("name", ""), "合計": r["total"]}
            for k, v in r["scores"].items():
                row[k.split("_", 1)[1]] = v
            rows.append(row)
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 各選手の特記事項
        for r in scored:
            if r.get("notes"):
                notes_str = " / ".join(r["notes"])
                st.markdown(f"**{r['course']}C {r.get('name','')}**: {notes_str}")

    # 展開シナリオ
    st.markdown(f"""
    <div class="card">
        <div class="card-title" style="color:#64B5F6">🌊 展開シナリオ</div>
        <div style="font-size:14px;line-height:1.8;color:#ccc">{analysis['scenario']}</div>
        <div style="margin-top:10px">
            <span style="display:inline-block;padding:5px 14px;background:rgba(100,181,246,0.15);
                         border-radius:20px;font-size:13px;font-weight:700;color:#64B5F6">
                決まり手予測: {analysis['pattern']}
            </span>
            <span style="display:inline-block;padding:5px 14px;background:rgba(206,147,216,0.15);
                         border-radius:20px;font-size:13px;font-weight:700;color:#CE93D8;margin-left:8px">
                信頼度: {analysis['confidence']}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 推奨判定
    rec = analysis["recommendation"]
    rec_type = rec.get("type", "")

    if rec_type == "見送り":
        css_class = "rec-skip"
        icon = "⚠️"
        label_color = "#FF9800"
    elif rec_type == "注意":
        css_class = "rec-caution"
        icon = "⚡"
        label_color = "#FFEB3B"
    else:
        css_class = "rec-buy"
        icon = "🎯"
        label_color = "#4CAF50"

    formations_html = ""
    if rec.get("formations"):
        chips = "".join([f'<span class="formation-chip">{f}</span>' for f in rec["formations"]])
        formations_html = f"""
        <div style="margin-top:10px">
            <div style="font-size:11px;color:#888;margin-bottom:4px">
                {rec.get('bet_type', 'フォーメーション')}:
            </div>
            {chips}
        </div>
        """

    st.markdown(f"""
    <div class="{css_class}">
        <div style="font-size:12px;font-weight:700;color:{label_color};letter-spacing:1px;margin-bottom:6px">
            {icon} 推奨判定: <span style="font-size:18px">{rec_type}</span>
        </div>
        <div style="font-size:13px;line-height:1.7;color:#ccc">{rec.get('reason', '')}</div>
        {formations_html}
    </div>
    """, unsafe_allow_html=True)

    # 期待値判定
    bets = analysis.get("bets", [])
    if bets:
        st.markdown("""
        <div class="card" style="margin-top:14px">
            <div class="card-title" style="color:#CE93D8">💰 期待値判定（買い目候補）</div>
        </div>
        """, unsafe_allow_html=True)

        for b in bets:
            hit_pct = b["hit_rate"] * 100
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;
                        padding:8px 12px;border-bottom:1px solid rgba(255,255,255,0.04)">
                <div>
                    <span style="font-family:monospace;font-weight:800;font-size:16px;color:#fff">
                        {b['bet']}
                    </span>
                    <span style="font-size:11px;color:#888;margin-left:10px">{b['note']}</span>
                </div>
                <div style="text-align:right">
                    <div style="font-size:12px;color:#CE93D8">的中率 {hit_pct:.1f}%</div>
                    <div style="font-size:11px;color:#888">必要 {b['req_odds']}倍以上</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div style="font-size:11px;color:#666;margin-top:8px;padding:8px;
                    background:rgba(0,0,0,0.2);border-radius:6px">
            💡 期待値 = 想定的中率 × 実オッズ。1.0以上の買い目のみ購入推奨。
            実オッズが「必要倍率」以上であれば期待値1.0超です。
        </div>
        """, unsafe_allow_html=True)

    # ─── 過去レースの結果 & 払い戻し表示 ───
    is_past = selected_date < date.today()
    if is_past:
        with st.spinner("📋 レース結果を取得中..."):
            race_result = get_race_result_detail(selected_venue_jcd, date_str, selected_race)

        if race_result["has_result"]:
            st.markdown("""
            <div class="card" style="border-color:rgba(76,175,80,0.4);margin-top:14px">
                <div class="card-title" style="color:#4CAF50">🏆 レース結果</div>
            </div>
            """, unsafe_allow_html=True)

            # 着順表示
            if race_result["order"]:
                order_html = ""
                for o in sorted(race_result["order"], key=lambda x: x["rank"]):
                    rank = o["rank"]
                    course = o["course"]
                    badge = render_course_badge(course)
                    rank_icon = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}着")
                    name = o.get("name", "")
                    order_html += f"""
                    <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;
                                padding:6px 12px;background:{'rgba(245,197,24,0.06)' if rank <= 3 else 'transparent'};
                                border-radius:8px">
                        <span style="font-size:18px;min-width:30px">{rank_icon}</span>
                        {badge}
                        <span style="font-weight:700;color:{'#F5C518' if rank==1 else '#ccc'};font-size:14px">
                            {course}号艇 {name}
                        </span>
                    </div>
                    """
                st.markdown(order_html, unsafe_allow_html=True)

                # 予想との照合
                if race_result["order"]:
                    actual_1st = race_result["order"][0]["course"] if len(race_result["order"]) > 0 else None
                    pred_1st = scored[0]["course"] if scored else None
                    if actual_1st and pred_1st:
                        if actual_1st == pred_1st:
                            st.success(f"✅ 1着予想 的中！ ({pred_1st}C)")
                        else:
                            st.error(f"❌ 1着予想 不的中 (予想:{pred_1st}C → 結果:{actual_1st}C)")

                    # 買い目との照合
                    if len(race_result["order"]) >= 3:
                        actual_combo = f"{race_result['order'][0]['course']}-{race_result['order'][1]['course']}-{race_result['order'][2]['course']}"
                        hit_bets = [b for b in bets if b["bet"] == actual_combo]
                        if hit_bets:
                            st.success(f"🎯 3連単 {actual_combo} 的中！ (推奨買い目に含まれていました)")
                        else:
                            st.info(f"📊 確定3連単: {actual_combo}")

            # 払い戻し金表示
            if race_result["payouts"]:
                st.markdown("""
                <div class="card" style="border-color:rgba(206,147,216,0.4);margin-top:10px">
                    <div class="card-title" style="color:#CE93D8">💰 払い戻し金</div>
                </div>
                """, unsafe_allow_html=True)

                # 表示順を定義
                type_order = {"3連単": 1, "3連複": 2, "2連単": 3, "2連複": 4, "拡連複": 5, "単勝": 6, "複勝": 7}
                sorted_payouts = sorted(race_result["payouts"], key=lambda x: type_order.get(x["type"], 99))

                for p in sorted_payouts:
                    amount = p["amount"]
                    # 高額かどうかで色を変える
                    if amount >= 10000:
                        amt_color = "#F44336"
                        label = "🔥"
                    elif amount >= 3000:
                        amt_color = "#FF9800"
                        label = "⚡"
                    else:
                        amt_color = "#4CAF50"
                        label = ""

                    st.markdown(f"""
                    <div style="display:flex;justify-content:space-between;align-items:center;
                                padding:8px 14px;border-bottom:1px solid rgba(255,255,255,0.05)">
                        <div>
                            <span style="font-size:12px;font-weight:700;color:#aaa;min-width:60px;display:inline-block">
                                {p['type']}
                            </span>
                            <span style="font-family:monospace;font-size:14px;color:#ddd;margin-left:12px">
                                {p['combo']}
                            </span>
                        </div>
                        <div style="font-size:16px;font-weight:800;color:{amt_color}">
                            {label} ¥{amount:,}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("⚠️ 払い戻しデータを取得できませんでした。レース結果ページの構造が変わった可能性があります。")

            # 結果ページへのリンク
            hd_link = date_str.replace("-", "")
            result_url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={selected_race}&jcd={selected_venue_jcd}&hd={hd_link}"
            st.markdown(f"""
            <div style="text-align:center;margin-top:10px">
                <a href="{result_url}" target="_blank" style="color:#64B5F6;font-size:12px">
                    📎 公式結果ページを確認する
                </a>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("📋 このレースの結果はまだ確定していません。")

    # 注意事項
    st.markdown("""
    <div style="margin-top:20px;padding:12px;font-size:10px;color:#555;
                text-align:center;line-height:1.8;border-top:1px solid rgba(255,255,255,0.05)">
        ※ AI予想は参考情報です。購入は自己判断・自己責任でお願いします。<br>
        ※ ⑬コース別成績は個別選手ページ未取得のため0扱い。⑨節間動態は簡易評価。<br>
        ※ 展示タイム・風速は直前情報ページから取得。データ更新タイミングにより反映されない場合があります。<br>
        ※ 1日最大5レース / 1レース投資上限は日次予算の25%以内を推奨
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
