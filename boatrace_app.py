"""
🚤 ボートレース予想アプリ v14.6 (展示ST完全適用・全艇スリット可視化版)
━━━━━━━━━━━━━━━━━━━━━━━━
データソース: uchisankaku.sakura.ne.jp（事前データ）
             boatrace.jp（展示ST・直前情報・レース結果）
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
        if sanrentan and ranks: 
            return {"sanrentan": sanrentan, "ranks": ranks, "payout": payout_val}
    except: pass
    return None

# ─── 展示ST 取得機能 ───
def get_exhibition_st(jcd, ds, rno):
    hd = ds.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={hd}"
    ex_st = {}
    try:
        html = fetch(url)
        soup = BeautifulSoup(html, "html.parser")
        for tr in soup.find_all('tr'):
            cells = tr.find_all(['td', 'th'])
            if not cells: continue
            
            first_cell_class = cells[0].get('class', [])
            first_cell_text = cells[0].get_text(strip=True)
            
            if first_cell_text in ['1','2','3','4','5','6'] and any('is-boatColor' in c for c in first_cell_class):
                boat_no = int(first_cell_text)
                for cell in cells[1:]:
                    txt = cell.get_text(strip=True)
                    m = re.search(r'(F|L)?(\d\.\d{2})', txt)
                    if m:
                        if m.group(1): # F(フライング) or L(出遅れ)
                            ex_st[boat_no] = -0.01 
                        else:
                            ex_st[boat_no] = float(m.group(2))
                        break
    except: pass
    return ex_st

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
    base_st = r.get("course_st", 0.0)
    if base_st <= 0: base_st = r.get("session_st", 0.0)
    if base_st <= 0 or base_st == 0.15: base_st = r.get("avg_st", 0.15)
    
    if ex_st_val is None:
        return base_st
    if ex_st_val < 0:
        return base_st + 0.05
    if ex_st_val > 0.20:
        return (base_st * 0.4) + (ex_st_val * 0.6)
    return (base_st * 0.6) + (ex_st_val * 0.4)

def evaluate_all_patterns(racers, jcd, ex_st_dict):
    for r in racers:
        c = r["course"]
        ex_val = ex_st_dict.get(c, None)
        r["eff_st"] = calc_hybrid_st(r, ex_val)
        
    r1, r2, r3, r4, r5, r6 = racers
    st1, st2, st3, st4 = r1["eff_st"], r2["eff_st"], r3["eff_st"], r4["eff_st"]
    nr1, nr2, nr3, nr4 = r1["national_rate"], r2["national_rate"], r3["national_rate"], r4["national_rate"]
    cl1, cl3, cl4 = r1["class"], r3["class"], r4["class"]

    targets = []

    c1_weak = (nr1 < 5.4 and cl1 not in ["A1", "A2"])
    c2_no_wall = (nr1 > nr2) 
    
    fatal_reasons = []
    if r1.get("f_count", 0) >= 1: fatal_reasons.append("1C-F持")
    if r1.get("motor_2ren", 33.0) < 30.0: fatal_reasons.append("1C-機力×")
    
    base_st1 = r1.get("course_st") if r1.get("course_st", 0) > 0 else r1.get("avg_st", 0.15)
    if base_st1 >= 0.17: fatal_reasons.append("1C-基礎ST遅")
    
    ex1 = ex_st_dict.get(1, None)
    if ex1 is not None:
        if ex1 < 0: fatal_reasons.append("1C-🔥展示F(致命的)")
        elif ex1 >= 0.18: fatal_reasons.append("1C-展示遅")

    if not c1_weak or not fatal_reasons or not c2_no_wall:
        return None

    # ─── 3コース一撃まくり ───
    if st2 >= st3:  
        if (cl3 in ["A1", "A2"] or nr3 >= 6.0) and (st3 <= 0.15):
            if st3 < st1: 
                score = nr3 + (6.0 - nr1) * 2 + IN_ADJ.get(jcd, 0)
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
    if nr3 < 5.5:  
        if (cl4 in ["A1", "A2"] or nr4 >= 6.0) and (st4 <= 0.15):
            if st3 >= st4 + 0.02 and st4 < st1:
                score = nr4 + (6.0 - nr1) * 2 + IN_ADJ.get(jcd, 0)
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

    # 【修正】全6艇の予想ST文字列生成
    pred_st_strs = []
    for r in racers:
        pred_st_strs.append(f"{r['course']}C({r['eff_st']:.2f})")
    st_info = " / ".join(pred_st_strs)

    # 【修正】全6艇の展示ST文字列生成
    ex_strs = []
    for i in range(1, 7):
        val = ex_st_dict.get(i)
        if val is None: ex_strs.append(f"{i}C(--)")
        elif val < 0: ex_strs.append(f"{i}C(F)")
        else: ex_strs.append(f"{i}C({val:.2f})")
    ex_st_info = " / ".join(ex_strs)

    return {
        "target": best["target"],
        "score": round(best["score"], 1),
        "stars": stars,
        "reasons": best["reasons"],
        "st_info": st_info,
        "ex_st_info": ex_st_info,
        "pw_info": f"1C({nr1:.1f}) 2C({nr2:.1f}) 3C({nr3:.1f}) 4C({nr4:.1f})",
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
    
    st.markdown('<div class="hdr"><span style="font-size:32px">🔥</span><div><h1>BOAT RACE AI</h1><div class="sub">v14.6 ─ 1号艇確殺 (全艇スリット可視化版)</div></div></div>',unsafe_allow_html=True)

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

                        # 展示STを取得
                        ex_st_dict = get_exhibition_st(jcd, ds, rno)
                        
                        ev = evaluate_all_patterns(racers, jcd, ex_st_dict)
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
