"""
🚤 ボートレース予想アプリ v9.1 (1-X展開 全方位ハンター / 1号艇超・鉄板特化版)
━━━━━━━━━━━━━━━━━━━━━━━━
データソース: uchisankaku.sakura.ne.jp（コース別・節間・全選手データ・決まり手）
             boatrace.jp（開催場一覧・直前情報・レース結果）
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
    2: "background:#000;color:#FFF;border:1px solid #555;",
    3: "background:#E8212A;color:#FFF;",
    4: "background:#1B6DB5;color:#FFF;",
    5: "background:#F5C518;color:#000;"
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

# ━━━━━━━━━━━ boatrace.jp(開催場・直前情報・結果) ━━━━━━━━━━━
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

def get_race_times(jcd,ds):
    hd=ds.replace("-",""); times={}
    try:
        text=BeautifulSoup(fetch(f"https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={jcd}&hd={hd}"),"html.parser").get_text()
        v=[]
        for t in re.findall(r'(\d{1,2}:\d{2})',text):
            if 8<=int(t.split(":")[0])<=21 and t not in v: v.append(t)
        for i,t in enumerate(v[:12]): times[i+1]=t
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
                    
        if not sanrentan:
            text_all = soup.get_text(separator=" ", strip=True)
            m = re.search(r'3連単\s*([1-6])\s*[\-\s]*([1-6])\s*[\-\s]*([1-6])\s*(?:¥)?([\d,]+)円?', text_all)
            if m: 
                ranks = [int(m.group(1)), int(m.group(2)), int(m.group(3))]
                payout_val = int(m.group(4).replace(',', ''))
                sanrentan = f"{m.group(1)}-{m.group(2)}-{m.group(3)}  {m.group(4)}円"
                
        if sanrentan and ranks: 
            return {"sanrentan": sanrentan, "ranks": ranks, "payout": payout_val}
    except: pass
    return None

# ━━━━━━━━━━━ uchisankaku(メインデータ) ━━━━━━━━━━━
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
        
        # --- F数（フライング）のパース ---
        f_s = gv("F数").replace("F", "")
        r["f_count"] = int(f_s) if f_s.isdigit() else 0

        # --- 勝率の確実なパース ---
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
            if re.match(r'^\d+\.\d+$', nr_s):
                r["national_rate"] = float(nr_s)

        # --- モーター2連率のパース ---
        in_motor = False
        motor_2ren = 33.0
        for tr in rows:
            cells = tr.find_all(["td","th"])
            texts2 = [c.get_text(strip=True) for c in cells]
            joined = " ".join(texts2)
            if "モーター" in joined or "ター" in joined: in_motor = True
            elif "今節成績" in joined: in_motor = False
            
            if in_motor and len(texts2) >= 7:
                data = texts2[-6:]
                label2 = " ".join(texts2[:-6]).strip()
                if "2連率" in label2:
                    val = data[i]
                    if re.match(r'^[\d.]+$', val) and float(val) > 0:
                        motor_2ren = float(val)
                        break
        r["motor_2ren"] = motor_2ren

        # --- 平均STのパース ---
        st_s = gv("ST")
        r["avg_st"] = float(st_s) if re.match(r'^0\.\d+$', st_s) else 0.15

        # --- 今節STのパース ---
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

# ━━━━━━━━━━━ メイン解析ロジック（全展開網羅） ━━━━━━━━━━━

def get_eff_st(r):
    """節間ST優先、未走なら平均ST"""
    s = r.get("session_st", 0)
    return s if (s > 0 and s != 0.15) else r.get("avg_st", 0.15)

def evaluate_all_patterns(racers, jcd):
    """1-2, 1-3, 1-4, 1-5の各展開をスコアリングし、最も期待値の高い展開を返す"""
    r1, r2, r3, r4, r5, r6 = racers
    st1, st2, st3, st4, st5, st6 = [get_eff_st(r) for r in racers]
    nr1, nr2, nr3, nr4, nr5, nr6 = [r.get("national_rate", 5.0) for r in racers]
    cl1, cl2, cl3, cl4, cl5, cl6 = [r.get("class", "B1") for r in racers]

    # ━━━ 1号艇「超・鉄板」絶対条件 ━━━
    
    # ① 級別・勝率フィルター (A1級、または勝率6.5以上必須)
    if cl1 != "A1" and nr1 < 6.5: return None
    
    # ② スタートフィルター (0.15以内必須)
    if st1 > 0.15: return None
    
    # ③ フライング(F)持ち排除 (スタートで無理できないため除外)
    if r1.get("f_count", 0) >= 1: return None
    
    # ④ 圧倒的実力フィルター (出走メンバー内で勝率単独トップ必須)
    max_rival_nr = max([nr2, nr3, nr4, nr5, nr6])
    if nr1 <= max_rival_nr: return None
    
    # ⑤ 最低限のモーター確保 (2連率30%未満は除外)
    if r1.get("motor_2ren", 33) < 30.0: return None

    # ここまで残った1号艇は極めて信頼度が高い
    base_score = 5  # 基礎点を付与
    reasons_base = ["1C超鉄板(F0/勝率1位)"]
    if nr1 >= 7.0: base_score += 4; reasons_base.append(f"1C勝率{nr1:.1f}")
    if r1.get("motor_2ren", 33) >= 40: base_score += 2; reasons_base.append("1C機力◎")
    
    in_adj = IN_ADJ.get(jcd, 0)
    if in_adj >= 1.5: base_score += 1
    elif in_adj <= -1.5: base_score -= 1

    patterns = []

    # ─── 1-2展開の評価 ───
    def eval_12():
        if nr2 < 5.0: return -1, []
        if st3 < st2 - 0.03 and cl3 in ["A1", "A2"]: return -1, []
        
        sc = 0; rs = []
        if nr2 >= 6.5: sc += 5; rs.append(f"2C勝率{nr2:.1f}")
        elif nr2 >= 6.0: sc += 3; rs.append(f"2C勝率{nr2:.1f}")
        if cl2 == "A1": sc += 3; rs.append("2C=A1級")
        
        if st2 <= 0.14: sc += 2; rs.append("2C好ST")
        if nr2 >= nr3 + 0.5: sc += 2; rs.append("2C>3C勝率")
        if nr3 < 5.5 and nr4 < 5.5: sc += 3; rs.append("中枠脅威なし")
        
        if st3 < st2: sc -= 3; rs.append("3C先行スリット")
        return sc, rs

    s_12, r_12 = eval_12()
    if s_12 >= 0 and base_score + s_12 >= 15: # 基準点を少し引き上げ
        patterns.append({"target": 2, "score": base_score + s_12, "reasons": reasons_base + r_12})

    # ─── 1-3展開の評価 ───
    def eval_13():
        if nr2 >= nr3 and st2 <= st3 + 0.01: return -1, []
        if cl2 == "A1": return -1, []
        if nr3 < 5.0: return -1, []
        if st4 < st3 - 0.03 and cl4 in ["A1", "A2"]: return -1, []
        
        sc = 0; rs = []
        if st3 < st2 - 0.03: sc += 5; rs.append(f"3C先行({st3:.2f}<{st2:.2f})")
        elif st3 < st2: sc += 3; rs.append("3C-ST優位")
        else: sc -= 3
        
        if nr3 - nr2 >= 1.5: sc += 5; rs.append(f"3C勝率圧倒({nr3:.1f}>{nr2:.1f})")
        elif nr3 - nr2 >= 0.5: sc += 3; rs.append("3C勝率優位")
        
        if cl3 == "A1": sc += 3; rs.append("3C=A1級")
        if r3.get("motor_2ren", 33) >= 40: sc += 2; rs.append("3C機力◎")
        if st4 >= st3 + 0.02: sc += 2; rs.append("4C遅れ")
        return sc, rs

    s_13, r_13 = eval_13()
    if s_13 >= 0 and base_score + s_13 >= 15:
        patterns.append({"target": 3, "score": base_score + s_13, "reasons": reasons_base + r_13})

    # ─── 1-4展開の評価 ───
    def eval_14():
        if nr4 < 5.0: return -1, []
        if nr3 >= 6.0 and st3 <= 0.14: return -1, [] 
        if st4 < st1 - 0.04 and nr4 >= 6.5: return -1, []
        
        sc = 0; rs = []
        if st3 > st4 + 0.02: sc += 5; rs.append(f"3C凹み({st3:.2f}>{st4:.2f})")
        if nr4 - nr3 >= 1.0: sc += 3; rs.append(f"4C>3C勝率({nr4:.1f}>{nr3:.1f})")
        if cl4 == "A1": sc += 3; rs.append("4C=A1級")
        if st4 <= 0.14: sc += 3; rs.append("4C好ST")
        if r4.get("motor_2ren", 33) >= 40: sc += 2; rs.append("4C機力◎")
        
        if st2 >= 0.17 and st3 >= 0.17: sc += 3; rs.append("内枠ST不安")
        return sc, rs

    s_14, r_14 = eval_14()
    if s_14 >= 0 and base_score + s_14 >= 15:
        patterns.append({"target": 4, "score": base_score + s_14, "reasons": reasons_base + r_14})

    # ─── 1-5展開の評価 ───
    def eval_15():
        if nr5 < 5.5: return -1, [] 
        if st4 >= 0.19 and st5 >= 0.18: return -1, [] 
        
        sc = 0; rs = []
        if nr5 >= 6.5: sc += 5; rs.append(f"5C勝率高({nr5:.1f})")
        if cl5 == "A1": sc += 3; rs.append("5C=A1級")
        
        if st4 <= 0.14 and st5 <= 0.15: sc += 3; rs.append("4-5連動ST")
        if nr5 - nr4 >= 1.0: sc += 3; rs.append(f"5C>4C勝率({nr5:.1f}>{nr4:.1f})")
        if r5.get("motor_2ren", 33) >= 40: sc += 2; rs.append("5C機力◎")
        
        if nr4 < 5.0 and st4 <= 0.15: sc += 2; rs.append("4C攻め5C展開")
        return sc, rs

    s_15, r_15 = eval_15()
    if s_15 >= 0 and base_score + s_15 >= 15:
        patterns.append({"target": 5, "score": base_score + s_15, "reasons": reasons_base + r_15})

    # ━━━ 最適展開の決定 ━━━
    if not patterns: return None

    best_pattern = max(patterns, key=lambda x: x["score"])
    target = best_pattern["target"]
    sc = best_pattern["score"]
    
    stars = "★★★" if sc >= 22 else "★★☆" if sc >= 18 else "★☆☆"

    return {
        "target": target,
        "score": round(sc, 1),
        "stars": stars,
        "reasons": best_pattern["reasons"],
        "st_info": f"1C({st1:.2f}) 2C({st2:.2f}) 3C({st3:.2f}) 4C({st4:.2f}) 5C({st5:.2f})",
        "pw_info": f"1C({nr1:.1f}) 2C({nr2:.1f}) 3C({nr3:.1f}) 4C({nr4:.1f}) 5C({nr5:.1f})",
        "pred_str": f"1-{target}-全",
    }

# ━━━━━━━━━━━ 日付リスト生成 ━━━━━━━━━━━
def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)

# ━━━━━━━━━━━ UI ━━━━━━━━━━━
def main():
    st.set_page_config(page_title="🚤 1-X展開 全方位ハンター",page_icon="🚤",layout="wide",initial_sidebar_state="collapsed")
    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap');
    .stApp{background:linear-gradient(135deg,#0a0a1a,#0d1b2a 40%,#1b2838);font-family:'Noto Sans JP',sans-serif}
    .hdr{background:linear-gradient(90deg,#E8212A,#B71C1C);padding:16px 24px;border-radius:12px;display:flex;align-items:center;gap:14px;box-shadow:0 4px 20px rgba(232,33,42,0.35);margin-bottom:16px}
    .hdr h1{color:#FFF!important;font-size:22px!important;font-weight:900!important;letter-spacing:3px;margin:0!important;padding:0!important}
    .hdr .sub{color:#ffcdd2;font-size:11px;letter-spacing:1px}
    .card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:16px;margin-bottom:12px}
    .sl{font-size:12px;font-weight:700;color:#E8212A;letter-spacing:2px;margin-bottom:8px}
    </style>""",unsafe_allow_html=True)
    
    st.markdown('<div class="hdr"><span style="font-size:32px">🚤</span><div><h1>BOAT RACE AI</h1><div class="sub">v9.1 ─ 1-X展開 全方位ハンター (1号艇 超・鉄板特化)</div></div></div>',unsafe_allow_html=True)

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

    if st.button(f"🎯 指定期間をまとめて解析（1-X展開）", type="primary", use_container_width=True):
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

                        ev = evaluate_all_patterns(racers, jcd)
                        if not ev: continue

                        target = ev["target"]
                        
                        race_info = {
                            "date": ds,
                            "jcd": jcd, "name": v["name"], "rno": rno,
                            "time": rtimes.get(rno, "--:--"),
                            "target": target,
                            "pred_str": ev["pred_str"],
                            "st_info": ev["st_info"],
                            "pw_info": ev["pw_info"],
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
                            invested += 400 # 4点(全)×100円

                            # 動的に買い目(1-target-全)を生成
                            buy_patterns = [[1, target, i] for i in range(1, 7) if i not in (1, target)]

                            if res["ranks"] in buy_patterns:
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
        st.markdown(f"<h3 style='margin-bottom:4px;'>🎯 超・鉄板 予想一覧 ({date_range_str}): 計 {len(matches)} 件</h3>", unsafe_allow_html=True)
        
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

                sc = m["score"]
                sc_color = "#F5C518" if sc >= 22 else "#E8212A" if sc >= 18 else "#ff8c00"

                reason_tags = " ".join(
                    f"<span style='background:rgba(255,255,255,0.08);padding:1px 6px;border-radius:3px;font-size:11px;color:#ccc;margin-right:4px;'>{r}</span>"
                    for r in m["reasons"]
                )

                tgt = m["target"]
                badge_css = COURSE_CSS.get(tgt, "background:#999;color:#fff;")
                tgt_badge = f"<span style='{badge_css} padding:3px 8px; border-radius:4px; font-weight:bold; font-size:13px; margin-right:8px;'>1-{tgt}展開</span>"
                
                race_date_str = m['date'][5:].replace("-", "/")

                card_html = (
                    f"<div style='background:{bg_color}; padding:12px 16px; border-radius:8px; {border_s} margin-bottom:10px;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;'>"
                    f"<div>{tgt_badge}<span style='color:#E8212A;font-weight:bold;font-size:16px;'>[{race_date_str}] {m['name']} {m['rno']}R</span>"
                    f"<span style='color:#ccc; font-size:13px; margin-left:8px;'>🕒 {m['time']}</span></div>"
                    f"<div style='display:flex;align-items:center;gap:8px;'>"
                    f"<span style='color:{sc_color};font-weight:900;font-size:18px;'>{m['stars']}</span>"
                    f"<span style='color:{sc_color};font-size:14px;font-weight:bold;'>{m['score']}pt</span>"
                    f"{hit_badge}{miss_1c}</div></div>"
                    f"<div style='font-size:11px; color:#888; margin-bottom:2px;'>ST : {m['st_info']}</div>"
                    f"<div style='font-size:11px; color:#888; margin-bottom:4px;'>勝率: {m['pw_info']}</div>"
                    f"<div style='margin-bottom:6px;'>{reason_tags}</div>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; font-size:15px; padding-top:4px; border-top:1px dashed rgba(255,255,255,0.1);'>"
                    f"<div style='color:#F5C518;'><span style='font-size:12px; color:#aaa;'>買い目:</span> "
                    f"<span style='font-weight:900; font-size:17px; letter-spacing:1px;'>{m['pred_str']} (4点)</span></div>"
                    f"<div style='text-align:right;'><span style='font-size:12px; color:#aaa;'>結果:</span> "
                    f"<span style='font-weight:bold;'>{m['result_str']}</span></div>"
                    f"</div></div>"
                )
                st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning("指定された期間・条件に合致するレースは見つかりませんでした。")

        if st.button("✖ 検索結果を閉じる", key="close_search"):
            st.session_state["search_done"] = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

if __name__=="__main__":
    main()
