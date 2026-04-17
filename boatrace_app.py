"""
🚤 ボートレース予想アプリ v14.9 (展示ST完全修復・気象情報対応版)
━━━━━━━━━━━━━━━━━━━━━━━━
データソース: uchisankaku.sakura.ne.jp（事前データ）
             boatrace.jp（展示ST・直前情報・気象情報・レース結果）

v14.9 修正内容:
 ▸ 展示ST取得を完全書き直し（BeautifulSoupベース）
 ▸ boatrace.jpの実HTML構造（.15形式/F.04形式）に対応
 ▸ 気象情報（風速・風向・波高・気温）の取得と表示を追加
 ▸ モーター行検出の誤判定修正（"ター"→"モーター"）
 ▸ calc_hybrid_stのデフォルト判定バグ修正
 ▸ get_race_timesを締切時刻行からの正規抽出に改善
"""
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import date, timedelta
import time

# ━━━━━━━━━━━ 定数 ━━━━━━━━━━━
VENUES = {
    "01":"桐生","02":"戸田","03":"江戸川","04":"平和島","05":"多摩川",
    "06":"浜名湖","07":"蒲郡","08":"常滑","09":"津","10":"三国",
    "11":"びわこ","12":"住之江","13":"尼崎","14":"鳴門","15":"丸亀",
    "16":"児島","17":"宮島","18":"徳山","19":"下関","20":"若松",
    "21":"芦屋","22":"福岡","23":"唐津","24":"大村",
}
IN_ADJ = {"18":3,"24":3,"21":3,"19":1.5,"12":1.5,"15":1.5,
           "02":-3,"03":-3,"04":-3,"01":-1.5,"05":-1.5,"11":-1.5}

UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "ja,en;q=0.9"}

COURSE_CSS = {
    3: "background:#E8212A;color:#FFF;",
    4: "background:#1B6DB5;color:#FFF;",
}

# 16方位マッピング（boatrace.jp is-wind{N} クラスの標準定義）
WIND_DIRECTIONS = {
    1:"↓無風", 2:"↙北東", 3:"←東北東", 4:"←東", 5:"←東南東",
    6:"↖南東", 7:"↑南南東", 8:"↑南", 9:"↑南南西", 10:"↗南西",
    11:"→西南西", 12:"→西", 13:"→西北西", 14:"↘北西",
    15:"↓北北西", 16:"↓北", 17:"↓北北東",
}
# boatrace.jp の is-wind{N} は 0=無風で 1-16 が方位 (実運用)
WIND_SIMPLE = {
    0:"無風",  1:"北", 2:"北北東", 3:"北東", 4:"東北東",
    5:"東",    6:"東南東", 7:"南東", 8:"南南東",
    9:"南",   10:"南南西", 11:"南西", 12:"西南西",
    13:"西",  14:"西北西", 15:"北西", 16:"北北西",
}

# ━━━━━━━━━━━ 共通 ━━━━━━━━━━━
@st.cache_data(ttl=180)
def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.encoding = "utf-8"
        return r.text
    except:
        return ""

def get_active_venues(ds):
    hd=ds.replace("-","")
    try:
        soup=BeautifulSoup(fetch(f"https://www.boatrace.jp/owpc/pc/race/index?hd={hd}"),"html.parser")
        seen,out=set(),[]
        for a in soup.find_all("a",href=True):
            if "raceindex" in a["href"] and f"hd={hd}" in a["href"]:
                m=re.search(r"jcd=(\d{2})",a["href"])
                if m and m.group(1) in VENUES and m.group(1) not in seen:
                    j=m.group(1); seen.add(j)
                    out.append({"jcd":j,"name":VENUES[j],"in_adj":IN_ADJ.get(j,0)})
        return out
    except: return []

def get_race_times(jcd, ds):
    """raceindex ページから各レースの締切時刻を取得（堅牢版）"""
    hd = ds.replace("-", "")
    times = {}
    try:
        html = fetch(f"https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={jcd}&hd={hd}")
        soup = BeautifulSoup(html, "html.parser")
        tp = re.compile(r'^\d{1,2}:\d{2}$')

        # 1) 「締切」を含む行を優先的に抽出
        for tr in soup.find_all('tr'):
            texts = [c.get_text(strip=True) for c in tr.find_all(['td','th'])]
            joined = " ".join(texts)
            if "締切" in joined or "締め切り" in joined:
                race_times = [t for t in texts if tp.match(t)]
                for i, t in enumerate(race_times[:12]):
                    times[i+1] = t
                if times: return times

        # 2) フォールバック: 全テキストからHH:MM抽出（8-23時）
        text = soup.get_text()
        v = []
        for t in re.findall(r'(\d{1,2}:\d{2})', text):
            try:
                h = int(t.split(":")[0])
                if 8 <= h <= 23 and t not in v:
                    v.append(t)
            except: pass
        for i, t in enumerate(v[:12]):
            times[i+1] = t
    except: pass
    return times

def get_official_result(jcd, ds, rno):
    hd = ds.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={jcd}&hd={hd}"
    try:
        html = fetch(url)
        if "3連単" not in html: return None
        soup = BeautifulSoup(html, "html.parser")
        sanrentan = ""
        ranks = []
        payout_val = 0

        for tr in soup.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) >= 3:
                header = tds[0].get_text(strip=True)
                if "3連単" in header:
                    combo = tds[1].get_text(strip=True)
                    payout_str = tds[2].get_text(strip=True)
                    sanrentan = f"{combo}  {payout_str}"
                    if "円" not in sanrentan: sanrentan += "円"
                    m_combo = re.findall(r'([1-6])', combo)
                    if len(m_combo) >= 3: ranks = [int(x) for x in m_combo[:3]]
                    m_payout = re.sub(r'[^\d]', '', payout_str)
                    if m_payout: payout_val = int(m_payout)
                    break
        if sanrentan and ranks:
            return {"sanrentan": sanrentan, "ranks": ranks, "payout": payout_val}
    except: pass
    return None

# ─── 展示ST 取得（boatrace.jp公式クラス名 table1_boatImage1 ベース） ───
def _parse_st_time_str(s):
    """
    boatrace.jp の展示ST文字列を float化。
    例: ".08" → 0.08 / "0.08" → 0.08 / "F.04" → -0.04 / "L.05" → 1.0 相当のエラー
    戻り値: (st値, is_flying)
      - 通常: (0.xx, False)
      - F: (0.xx, True) ※F付きのタイミング値として返す
      - L/欠場/不正: (None, False)
    """
    if not s:
        return (None, False)
    s = s.strip()
    # F.04 や L.05 を処理
    is_f = s.startswith('F')
    is_l = s.startswith('L')
    if is_f or is_l:
        s_num = s[1:]
    else:
        s_num = s
    # ".08" → "0.08" 正規化
    if s_num.startswith('.'):
        s_num = "0" + s_num
    m = re.match(r'^(\d+\.\d{2})$', s_num)
    if not m:
        return (None, False)
    try:
        v = float(m.group(1))
    except ValueError:
        return (None, False)
    if v >= 1.0:
        return (None, False)
    if is_l:
        # L（出遅れ）はタイミング自体が異常に遅い扱い
        return (None, False)
    return (v, is_f)

def get_exhibition_st(jcd, ds, rno):
    """
    boatrace.jp の beforeinfo ページから「スタート展示」の艇別STを取得する。
    boatrace.jp公式HTML構造:
       <span class="table1_boatImage1">
           <span class="table1_boatImage1Number">艇番</span>
           <span class="table1_boatImage1Time">ST値</span>
       </span>
    ※ "1" は固定文字列（艇番ではない）。6艇分の同クラス要素がコース順で並ぶ。

    戻り値: {艇番: ST値}
       - 通常: 0.xx の float
       - F(フライング): -0.01 (ペナルティマーカー)
    """
    hd = ds.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={hd}"
    ex_st = {}
    try:
        html = fetch(url)
        if not html: return ex_st
        soup = BeautifulSoup(html, "html.parser")

        # ─── 戦略A: 公式クラス名 table1_boatImage1 で直接取得 ───
        entries = soup.find_all(class_="table1_boatImage1")
        for entry in entries:
            num_elem = entry.find(class_="table1_boatImage1Number")
            time_elem = entry.find(class_="table1_boatImage1Time")
            if not num_elem or not time_elem:
                continue
            num_txt = num_elem.get_text(strip=True)
            time_txt = time_elem.get_text(strip=True)
            if not num_txt.isdigit():
                continue
            boat_no = int(num_txt)
            if not (1 <= boat_no <= 6):
                continue
            st_val, is_f = _parse_st_time_str(time_txt)
            if st_val is None:
                continue
            ex_st[boat_no] = -0.01 if is_f else st_val

        if ex_st:
            return ex_st

        # ─── 戦略B: HTML生テキストから直接正規表現で抽出（フォールバック） ───
        # table1_boatImage1Number と table1_boatImage1Time のペアを近傍から発見
        for m in re.finditer(
            r'class="[^"]*table1_boatImage1Number[^"]*"[^>]*>\s*(\d)\s*<'
            r'(?:.(?!table1_boatImage1Number))*?'
            r'class="[^"]*table1_boatImage1Time[^"]*"[^>]*>\s*([^<]+?)\s*<',
            html, flags=re.DOTALL):
            try:
                boat_no = int(m.group(1))
            except ValueError:
                continue
            if not (1 <= boat_no <= 6):
                continue
            st_val, is_f = _parse_st_time_str(m.group(2))
            if st_val is None:
                continue
            if boat_no not in ex_st:
                ex_st[boat_no] = -0.01 if is_f else st_val

    except Exception:
        pass
    return ex_st

# ─── 気象情報取得（新規追加） ───
def get_weather_info(jcd, ds, rno):
    """
    beforeinfo ページから気象情報を抽出。
    戻り値: {"wind_speed": float, "wind_dir": str, "wind_dir_num": int,
            "wave_height": int, "temperature": float, "water_temp": float,
            "weather": str}
    取得失敗項目は None。
    """
    hd = ds.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={hd}"
    info = {"wind_speed": None, "wind_dir": None, "wind_dir_num": None,
            "wave_height": None, "temperature": None, "water_temp": None,
            "weather": None}
    try:
        html = fetch(url)
        if not html: return info
        soup = BeautifulSoup(html, "html.parser")

        # ─── 戦略A: boatrace.jp公式クラス名で取得 ───
        # weather1_bodyUnitLabelData は [気温, 風速, 水温, 波高] の順に4個並ぶ
        labels = soup.find_all(class_="weather1_bodyUnitLabelData")
        if len(labels) >= 4:
            try:
                info["temperature"] = float(re.sub(r'[^\d.]', '', labels[0].get_text()))
            except: pass
            try:
                info["wind_speed"] = float(re.sub(r'[^\d.]', '', labels[1].get_text()))
            except: pass
            try:
                info["water_temp"] = float(re.sub(r'[^\d.]', '', labels[2].get_text()))
            except: pass
            try:
                info["wave_height"] = int(re.sub(r'[^\d]', '', labels[3].get_text()))
            except: pass

        # 天候名（晴/曇/雨/雪）— weather1_bodyUnitLabelTitle の中から天候語を検索
        weather_words = {"晴", "曇", "雨", "雪", "霧", "雷"}
        titles = soup.find_all(class_="weather1_bodyUnitLabelTitle")
        for t in titles:
            wt = t.get_text(strip=True)
            if wt in weather_words:
                info["weather"] = wt
                break

        # 風向（公式は p.is-wind{N} 形式、0=無風、1-16=16方位）
        dir_num = None
        for p in soup.find_all(class_=re.compile(r'\bis-wind\d+')):
            classes = p.get('class') or []
            for cl in classes:
                m = re.match(r'is-wind(\d{1,2})$', cl)
                if m:
                    dir_num = int(m.group(1))
                    break
            if dir_num is not None: break

        # ─── 戦略B: 戦略Aで取れない項目をテキスト正規表現でフォールバック ───
        text = soup.get_text(" ", strip=True)
        if info["temperature"] is None:
            m = re.search(r'気温\s*(\d+(?:\.\d+)?)\s*℃', text)
            if m: info["temperature"] = float(m.group(1))
        if info["water_temp"] is None:
            m = re.search(r'水温\s*(\d+(?:\.\d+)?)\s*℃', text)
            if m: info["water_temp"] = float(m.group(1))
        if info["wind_speed"] is None:
            m = re.search(r'風速\s*(\d+(?:\.\d+)?)\s*m', text)
            if m: info["wind_speed"] = float(m.group(1))
        if info["wave_height"] is None:
            m = re.search(r'波高\s*(\d+)\s*cm', text)
            if m: info["wave_height"] = int(m.group(1))
        if info["weather"] is None:
            m = re.search(r'℃\s*(晴|曇|雨|雪|霧|雷)', text)
            if m: info["weather"] = m.group(1)
        if dir_num is None:
            # 生HTML直接正規表現
            for pat in (r'class="[^"]*\bis-wind(\d{1,2})\b', r'is-windDirection(\d{1,2})'):
                m = re.search(pat, html)
                if m:
                    dir_num = int(m.group(1))
                    break

        if dir_num is not None:
            info["wind_dir_num"] = dir_num
            info["wind_dir"] = WIND_SIMPLE.get(dir_num, f"方位{dir_num}")
    except Exception:
        pass
    return info

@st.cache_data(ttl=120)
def get_uchi_data(jcd, ds):
    jcode = str(int(jcd))
    hd = ds.replace("-","")
    url = f"https://uchisankaku.sakura.ne.jp/racelist.php?jcode={jcode}&date={hd}"
    return fetch(url)

def parse_uchi_race(html, race_no):
    soup = BeautifulSoup(html, "html.parser")
    racers = []
    target_h3 = None
    for h3 in soup.find_all("h3"):
        if re.search(rf'{race_no}R', h3.get_text(strip=True)):
            target_h3 = h3
            break
    if not target_h3: return []
    tbl = target_h3.find_next("table")
    if not tbl: return []
    rows = tbl.find_all("tr")
    row_map = {}

    for tr in rows:
        cells = tr.find_all(["td","th"])
        texts = [c.get_text(strip=True) for c in cells]
        if len(texts) < 7: continue
        data6 = texts[-6:]
        label = ""
        for t in texts[:-6]:
            t = t.replace("　"," ").strip()
            if t and t not in ("選手情報","成績","コース別／直近６カ月","決り手","モーター","今節成績","","枠"):
                label = t
                break
        if not label and len(texts) > 7:
            for t in texts[:3]:
                t = t.strip()
                if t and t not in ("","選手情報","成績"):
                    label = t
                    break
        if label: row_map[label] = data6

    for i in range(6):
        r = {"course": i+1}
        def gv(label, idx=i):
            return row_map.get(label, ["","","","","",""])[idx].strip() if label in row_map else ""

        r["name"] = gv("氏名")
        r["class"] = gv("級別") or "B1"
        r["national_rate"] = 5.0

        f_s = gv("F数").replace("F", "")
        r["f_count"] = int(f_s) if f_s.isdigit() else 0

        in_national = False
        nat_rate = None
        for tr in rows:
            cells = tr.find_all(["td","th"])
            texts2 = [c.get_text(strip=True) for c in cells]
            joined = " ".join(texts2)
            if "全国" in joined: in_national = True
            elif "当地" in joined or "コース別" in joined: in_national = False
            if len(texts2) >= 7:
                data = texts2[-6:]
                label2 = " ".join(texts2[:-6]).strip()
                if "勝率" in label2:
                    val = data[i]
                    if re.match(r'^\d+\.\d+$', val):
                        if in_national and nat_rate is None:
                            nat_rate = float(val)

        if nat_rate is not None:
            r["national_rate"] = nat_rate
        else:
            nr_s = gv("勝率")
            if re.match(r'^\d+\.\d+$', nr_s): r["national_rate"] = float(nr_s)

        # ── モーター2連率（"ター"部分一致バグを修正: "モーター"完全マッチへ） ──
        in_motor = False
        motor_2ren = 33.0
        for tr in rows:
            cells = tr.find_all(["td","th"])
            texts2 = [c.get_text(strip=True) for c in cells]
            joined = " ".join(texts2)
            if "モーター" in joined: in_motor = True
            elif "今節成績" in joined or "決り手" in joined: in_motor = False
            if in_motor and len(texts2) >= 7:
                data = texts2[-6:]
                label2 = " ".join(texts2[:-6]).strip()
                if "2連率" in label2:
                    val = data[i]
                    if re.match(r'^[\d.]+$', val) and float(val) > 0:
                        motor_2ren = float(val)
                        break
        r["motor_2ren"] = motor_2ren

        r["avg_st"] = float(gv("ST")) if re.match(r'^0\.\d+$', gv("ST")) else 0.15

        in_course_sec = False
        course_st = 0.0
        for tr in rows:
            cells = tr.find_all(["td","th"])
            texts2 = [c.get_text(strip=True) for c in cells]
            if len(texts2) < 7: continue
            label_str = "".join(texts2[:-6])
            if "コース別" in label_str: in_course_sec = True
            elif any(k in label_str for k in ["決り手", "モーター", "今節成績"]): in_course_sec = False

            if in_course_sec and ("ST" in label_str or "ＳＴ" in label_str):
                val = texts2[-6:][i]
                if re.match(r'^0\.\d+$', val):
                    course_st = float(val)
        r["course_st"] = course_st

        in_session = False
        session_st = 0.15
        for tr in rows:
            cells = tr.find_all(["td","th"])
            texts2 = [c.get_text(strip=True) for c in cells]
            joined = " ".join(texts2)
            if "今節成績" in joined: in_session = True
            elif in_session and len(texts2) >= 7:
                data = texts2[-6:]
                label2 = " ".join(texts2[:-6]).strip()
                val = data[i]
                if not val or val == "-": continue
                if "ST" in label2 and re.match(r'^[\d.]+$', val):
                    session_st = float(val)
        r["session_st"] = session_st

        racers.append(r)
    return racers

# ━━━━━━━━━━━ メイン解析ロジック ━━━━━━━━━━━

def calc_hybrid_st(r, ex_st_val):
    """展示STと事前STを合成して有効STを算出
    v14.9: 0.15(デフォルト値)判定を排除し、明示フラグで制御
    """
    # ベースSTの選出（優先度: course_st > session_st > avg_st）
    base_st = r.get("course_st", 0.0)
    has_valid_course = base_st > 0
    if not has_valid_course:
        session_st = r.get("session_st", 0.0)
        has_valid_session = (session_st > 0 and session_st != 0.15)  # 0.15はデフォルト
        if has_valid_session:
            base_st = session_st
        else:
            base_st = r.get("avg_st", 0.15)

    if ex_st_val is None:
        return base_st
    if ex_st_val < 0:  # 展示F or L
        return base_st + 0.05
    if ex_st_val > 0.20:
        return (base_st * 0.4) + (ex_st_val * 0.6)
    return (base_st * 0.6) + (ex_st_val * 0.4)

def evaluate_all_patterns(racers, jcd, ex_st_dict, weather=None):
    for r in racers:
        c = r["course"]
        ex_val = ex_st_dict.get(c, None)
        r["eff_st"] = calc_hybrid_st(r, ex_val)

    r1, r2, r3, r4, r5, r6 = racers
    st1, st2, st3, st4 = r1["eff_st"], r2["eff_st"], r3["eff_st"], r4["eff_st"]
    nr1, nr2, nr3, nr4 = r1["national_rate"], r2["national_rate"], r3["national_rate"], r4["national_rate"]

    targets = []

    # ━━━ 1号艇の致命傷判定 ━━━
    fatal_reasons = []
    if r1.get("f_count", 0) >= 1: fatal_reasons.append("1C-F持")
    if r1.get("motor_2ren", 33.0) < 30.0: fatal_reasons.append("1C-機力×")

    base_st1 = r1.get("course_st") if r1.get("course_st", 0) > 0 else r1.get("avg_st", 0.15)
    if base_st1 >= 0.18: fatal_reasons.append("1C-基礎ST遅")

    ex1 = ex_st_dict.get(1, None)
    if ex1 is not None:
        if ex1 < 0: fatal_reasons.append("1C-🔥展示F")
        elif ex1 >= 0.18: fatal_reasons.append("1C-展示遅")

    # 気象による致命傷加算（スコア基準③）
    if weather:
        ws = weather.get("wind_speed")
        wh = weather.get("wave_height")
        if ws is not None and ws >= 5.0:
            fatal_reasons.append(f"🌪風速{ws}m")
        if wh is not None and wh >= 8:
            fatal_reasons.append(f"🌊波高{wh}cm")

    is_c1_danger = (nr1 < 5.2) or (len(fatal_reasons) > 0)

    # ━━━ 2号艇壁無し判定 ━━━
    ex2 = ex_st_dict.get(2, None)
    is_c2_no_wall = False
    if nr2 < 5.4: is_c2_no_wall = True
    elif nr1 > nr2: is_c2_no_wall = True
    elif st2 >= 0.18: is_c2_no_wall = True
    elif ex2 is not None and ex2 >= 0.18: is_c2_no_wall = True

    if not is_c1_danger or not is_c2_no_wall:
        return None

    # ─── 3コース一撃まくり ───
    if st2 >= st3 - 0.02:
        if nr3 >= 5.5 and st3 <= 0.17:
            if st3 <= st1 + 0.03:
                score = nr3 + (6.0 - nr1) * 2 + (len(fatal_reasons) * 0.5) + IN_ADJ.get(jcd, 0)
                buy_patterns = [
                    [3,4,1], [3,4,5], [3,4,6],
                    [3,5,1], [3,5,4], [3,5,6],
                    [3,1,4], [3,1,5], [3,1,6]
                ]
                targets.append({
                    "target": 3,
                    "score": score,
                    "reasons": fatal_reasons + ["2C壁無・3C強攻"],
                    "pred_str": "3-145-1456 (9点)",
                    "buy_patterns": buy_patterns
                })

    # ─── 4コースカド一撃 ───
    if nr3 < 5.5 or st3 >= 0.18:
        if nr4 >= 5.5 and st4 <= 0.16:
            if st4 <= st1 + 0.03 and st4 <= st3:
                score = nr4 + (6.0 - nr1) * 2 + (len(fatal_reasons) * 0.5) + IN_ADJ.get(jcd, 0)
                buy_patterns = [[4,5,1], [4,5,6], [4,1,5], [4,1,6], [4,6,1], [4,6,5]]
                targets.append({
                    "target": 4,
                    "score": score,
                    "reasons": fatal_reasons + ["内枠崩れ・4C強攻"],
                    "pred_str": "4-156-156 (6点)",
                    "buy_patterns": buy_patterns
                })

    if not targets: return None

    best = max(targets, key=lambda x: x["score"])
    stars = "★★★" if best["score"] >= 8.0 else "★★☆"

    # 予想ST文字列
    pred_st_strs = [f"{r['course']}C({r['eff_st']:.2f})" for r in racers]
    st_info = " / ".join(pred_st_strs)

    # 展示ST文字列
    ex_strs = []
    for i in range(1, 7):
        val = ex_st_dict.get(i)
        if val is None: ex_strs.append(f"{i}C(--)")
        elif val < 0: ex_strs.append(f"{i}C(F)")
        else: ex_strs.append(f"{i}C({val:.2f})")
    ex_st_info = " / ".join(ex_strs)

    # 気象情報文字列
    weather_info = ""
    if weather:
        parts = []
        if weather.get("weather"): parts.append(weather["weather"])
        if weather.get("wind_speed") is not None:
            wd = weather.get("wind_dir") or ""
            parts.append(f"💨{wd}{weather['wind_speed']:.0f}m")
        if weather.get("wave_height") is not None:
            parts.append(f"🌊{weather['wave_height']}cm")
        if weather.get("temperature") is not None:
            parts.append(f"🌡{weather['temperature']:.0f}℃")
        weather_info = " ".join(parts)

    return {
        "target": best["target"],
        "score": round(best["score"], 1),
        "stars": stars,
        "reasons": best["reasons"],
        "st_info": st_info,
        "ex_st_info": ex_st_info,
        "pw_info": f"1C({nr1:.1f}) 2C({nr2:.1f}) 3C({nr3:.1f}) 4C({nr4:.1f})",
        "weather_info": weather_info,
        "pred_str": best["pred_str"],
        "buy_patterns": best["buy_patterns"]
    }

def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)

# ━━━━━━━━━━━ UI ━━━━━━━━━━━
def main():
    st.set_page_config(page_title="🚤 1号艇確殺ハイエナ",page_icon="🔥",layout="wide",initial_sidebar_state="collapsed")
    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap');
    .stApp{background:linear-gradient(135deg,#0a0a1a,#0d1b2a 40%,#1b2838);font-family:'Noto Sans JP',sans-serif}
    .hdr{background:linear-gradient(90deg,#E8212A,#B71C1C);padding:16px 24px;border-radius:12px;display:flex;align-items:center;gap:14px;box-shadow:0 4px 20px rgba(232,33,42,0.35);margin-bottom:16px}
    .hdr h1{color:#FFF!important;font-size:22px!important;font-weight:900!important;letter-spacing:3px;margin:0!important;padding:0!important}
    .hdr .sub{color:#ffcdd2;font-size:11px;letter-spacing:1px}
    .card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:16px;margin-bottom:12px}
    .sl{font-size:12px;font-weight:700;color:#E8212A;letter-spacing:2px;margin-bottom:8px}
    </style>""",unsafe_allow_html=True)

    st.markdown('<div class="hdr"><span style="font-size:32px">🔥</span><div><h1>BOAT RACE AI</h1><div class="sub">v14.9 ─ 展示ST完全修復・気象対応版</div></div></div>',unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="sl">STEP 1 ─ 対象期間（最大31日）</div>',unsafe_allow_html=True)
    sel_dates = st.date_input("対象期間", value=(date.today(), date.today()), label_visibility="collapsed")

    if isinstance(sel_dates, tuple):
        if len(sel_dates) == 2:
            s_date, e_date = sel_dates
        elif len(sel_dates) == 1:
            s_date = e_date = sel_dates[0]
        else:
            s_date = e_date = date.today()
    else:
        s_date = e_date = sel_dates

    st.markdown('</div>',unsafe_allow_html=True)

    if st.button(f"🎯 指定期間をまとめて解析（確殺ハイエナ）", type="primary", use_container_width=True):
        date_list = list(daterange(s_date, e_date))
        total_days = len(date_list)

        if total_days > 31:
            st.error("⚠️ 検索期間が長すぎます。サーバー負荷を防ぐため、31日以内で指定してください。")
            return

        with st.spinner(f"対象期間（計{total_days}日分）のレースを解析中..."):
            matches = []
            invested = 0
            returned = 0
            finished_count = 0

            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, current_date in enumerate(date_list):
                ds = current_date.strftime("%Y-%m-%d")
                status_text.text(f"🔍 解析中: {ds} ({i+1}/{total_days}日目)")

                venues = get_active_venues(ds)
                if not venues:
                    progress_bar.progress((i + 1) / total_days)
                    continue

                for v in venues:
                    jcd = v["jcd"]
                    html = get_uchi_data(jcd, ds)
                    if not html: continue
                    rtimes = get_race_times(jcd, ds)

                    for rno in range(1, 13):
                        racers = parse_uchi_race(html, rno)
                        if len(racers) < 6: continue

                        # 展示ST・気象情報を取得
                        ex_st_dict = get_exhibition_st(jcd, ds, rno)
                        weather = get_weather_info(jcd, ds, rno)

                        ev = evaluate_all_patterns(racers, jcd, ex_st_dict, weather)
                        if not ev: continue

                        race_info = {
                            "date": ds,
                            "jcd": jcd, "name": v["name"], "rno": rno,
                            "time": rtimes.get(rno, "--:--"),
                            "target": ev["target"],
                            "pred_str": ev["pred_str"],
                            "buy_patterns": ev["buy_patterns"],
                            "st_info": ev["st_info"],
                            "ex_st_info": ev["ex_st_info"],
                            "pw_info": ev["pw_info"],
                            "weather_info": ev.get("weather_info",""),
                            "score": ev["score"],
                            "stars": ev["stars"],
                            "reasons": ev["reasons"],
                            "is_finished": False,
                            "hit": False,
                            "result_str": "未確定",
                            "payout": 0,
                        }

                        res = get_official_result(jcd, ds, rno)
                        if res and res.get("ranks"):
                            race_info["is_finished"] = True
                            race_info["result_str"] = res["sanrentan"]
                            finished_count += 1

                            invested += len(race_info["buy_patterns"]) * 100

                            if res["ranks"] in race_info["buy_patterns"]:
                                race_info["hit"] = True
                                race_info["payout"] = res["payout"]
                                race_info["result_str"] = f"🎯 {res['sanrentan']}"
                                returned += res["payout"]

                        matches.append(race_info)

                progress_bar.progress((i + 1) / total_days)

            status_text.text(f"✅ 解析完了（計{total_days}日分）")
            time.sleep(1)
            status_text.empty()
            progress_bar.empty()

            matches.sort(key=lambda x: x["score"], reverse=True)

            st.session_state["search_matches"] = matches
            st.session_state["search_invested"] = invested
            st.session_state["search_returned"] = returned
            st.session_state["search_finished"] = finished_count
            st.session_state["search_done"] = True

    if st.session_state.get("search_done"):
        matches = st.session_state.get("search_matches", [])
        inv = st.session_state.get("search_invested", 0)
        ret = st.session_state.get("search_returned", 0)
        fin = st.session_state.get("search_finished", 0)
        roi = (ret / inv * 100) if inv > 0 else 0

        st.markdown('<div style="background:rgba(232, 33, 42, 0.1); padding:16px; border-radius:12px; border:1px solid #E8212A; margin-bottom:16px;">', unsafe_allow_html=True)
        date_range_str = f"{s_date.strftime('%m/%d')} 〜 {e_date.strftime('%m/%d')}" if s_date != e_date else f"{s_date.strftime('%m/%d')}"
        st.markdown(f"<h3 style='margin-bottom:4px;'>🎯 ハイエナ予想一覧 ({date_range_str}): 計 {len(matches)} 件</h3>", unsafe_allow_html=True)

        roi_color = "#2D8C3C" if roi >= 100 else "#E8212A" if roi > 0 else "#fff"

        dash_html = (
            f"<div style='display:flex; justify-content:space-around; background:rgba(0,0,0,0.3); padding:16px; border-radius:8px; margin-top:12px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.1);'>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>終了済</span><br><span style='font-size:22px;font-weight:bold;'>{fin} <span style='font-size:14px;'>件</span></span></div>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>投資</span><br><span style='font-size:22px;font-weight:bold;'>{inv:,} <span style='font-size:14px;'>円</span></span></div>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>払戻</span><br><span style='font-size:22px;font-weight:bold;color:{roi_color};'>{ret:,} <span style='font-size:14px;'>円</span></span></div>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>回収率</span><br><span style='font-size:24px;font-weight:900;color:{roi_color};'>{roi:.1f} <span style='font-size:16px;'>%</span></span></div>"
            f"</div>"
        )
        st.markdown(dash_html, unsafe_allow_html=True)

        if matches:
            for m in matches:
                bg_color = "rgba(45, 140, 60, 0.2)" if m["hit"] else "rgba(255,255,255,0.03)"
                border_s = "border:1px solid #2D8C3C;" if m["hit"] else "border:1px solid rgba(255,255,255,0.1);"
                hit_badge = "<span style='background:#2D8C3C; color:#fff; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:bold;'>的中🎯</span>" if m["hit"] else ""
                miss_1c = ""
                if m["is_finished"] and not m["hit"]:
                    miss_1c = "<span style='background:#E8212A; color:#fff; padding:2px 6px; border-radius:4px; font-size:11px;'>不的中</span>"

                sc_color = "#F5C518" if m["score"] >= 8.0 else "#E8212A"

                reason_tags = " ".join(
                    f"<span style='background:rgba(255,255,255,0.08);padding:1px 6px;border-radius:3px;font-size:11px;color:#ccc;margin-right:4px;'>{r}</span>"
                    for r in m["reasons"]
                )

                tgt = m["target"]
                badge_css = COURSE_CSS.get(tgt, "background:#999;color:#fff;")
                tgt_badge = f"<span style='{badge_css} padding:3px 8px; border-radius:4px; font-weight:bold; font-size:13px; margin-right:8px;'>{tgt}アタマ</span>"

                race_date_str = m['date'][5:].replace("-", "/")
                weather_line = ""
                if m.get("weather_info"):
                    weather_line = f"<div style='font-size:11px; color:#7EC8E3; margin-bottom:4px;'>🌏気象 : {m['weather_info']}</div>"

                card_html = (
                    f"<div style='background:{bg_color}; padding:12px 16px; border-radius:8px; {border_s} margin-bottom:10px;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;'>"
                    f"<div>{tgt_badge}<span style='color:#E8212A;font-weight:bold;font-size:16px;'>[{race_date_str}] {m['name']} {m['rno']}R</span>"
                    f"<span style='color:#ccc; font-size:13px; margin-left:8px;'>🕒 {m['time']}</span></div>"
                    f"<div style='display:flex;align-items:center;gap:8px;'>"
                    f"<span style='color:{sc_color};font-weight:900;font-size:18px;'>{m['stars']}</span>"
                    f"{hit_badge}{miss_1c}</div></div>"
                    f"<div style='font-size:11px; color:#aaa; margin-bottom:2px;'>🎯予想ST : {m['st_info']}</div>"
                    f"<div style='font-size:11px; color:#F5C518; margin-bottom:4px;'>🚤展示ST : {m['ex_st_info']}</div>"
                    f"{weather_line}"
                    f"<div style='font-size:11px; color:#888; margin-bottom:4px;'>勝率差 : {m['pw_info']}</div>"
                    f"<div style='margin-bottom:6px;'>{reason_tags}</div>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; font-size:15px; padding-top:4px; border-top:1px dashed rgba(255,255,255,0.1);'>"
                    f"<div style='color:#F5C518;'><span style='font-size:12px; color:#aaa;'>買い目:</span> "
                    f"<span style='font-weight:900; font-size:17px; letter-spacing:1px;'>{m['pred_str']}</span></div>"
                    f"<div style='text-align:right;'><span style='font-size:12px; color:#aaa;'>結果:</span> "
                    f"<span style='font-weight:bold;'>{m['result_str']}</span></div>"
                    f"</div></div>"
                )
                st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning("指定された期間に条件に合致するレースはありませんでした。")

        if st.button("✖ 検索結果を閉じる", key="close_search"):
            st.session_state["search_done"] = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

if __name__=="__main__":
    main()
