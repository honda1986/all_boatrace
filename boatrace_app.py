"""
🚤 ボートレース予想アプリ v4.9 (抽出ロジック切り替え＆極限厳選システム搭載)
━━━━━━━━━━━━━━━━━━━━━━━━
データソース: uchisankaku.sakura.ne.jp / boatrace.jp
"""
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import date
import time
import pandas as pd

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
ROUGH = {"02","03","04"}
NAT_REN3 = {1:81,2:59,3:54,4:50,5:37,6:22}
NAT_WIN1 = {1:55,2:15,3:12,4:11,5:6,6:2}

COURSE_CSS = {1:"background:#FFF;color:#000;border:1.5px solid #999;",
              2:"background:#000;color:#FFF;",3:"background:#E8212A;color:#FFF;",
              4:"background:#1B6DB5;color:#FFF;",5:"background:#F5C518;color:#000;",
              6:"background:#2D8C3C;color:#FFF;"}

UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "ja,en;q=0.9"}

# ━━━━━━━━━━━ 共通 ━━━━━━━━━━━
@st.cache_data(ttl=180)
def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.encoding = "utf-8"
    return r.text

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

def get_before_info(jcd,ds,rno):
    hd=ds.replace("-",""); res={"weather":{"wind_dir":"","wind_speed":0,"wave":0},"exhibition_times":{}}
    try:
        text=BeautifulSoup(fetch(f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={hd}"),"html.parser").get_text(separator=" ",strip=True)
        for wd in ["追い風","向かい風","右横風","左横風"]:
            if wd in text: res["weather"]["wind_dir"]=wd; break
        for m in re.finditer(r'(?<!\d)(\d{1,2})m(?![0-9])',text):
            ws=int(m.group(1))
            if 0<ws<=15: res["weather"]["wind_speed"]=ws; break
        wm=re.search(r'(\d{1,2})\s*cm',text)
        if wm: res["weather"]["wave"]=int(wm.group(1))
        for i,t in enumerate(re.findall(r'\b(6\.\d{2}|7\.\d{2})\b',text)[:6]):
            res["exhibition_times"][i+1]=float(t)
    except: pass
    return res

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

@st.cache_data(ttl=120)
def get_uchi_data(jcd, ds):
    jcode = str(int(jcd)) 
    hd = ds.replace("-","")
    url = f"https://uchisankaku.sakura.ne.jp/racelist.php?jcode={jcode}&date={hd}"
    try: return fetch(url)
    except: return ""

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

    session_results = {}
    for key, vals in row_map.items():
        m = re.match(r'^(\d+)走$', key)
        if m:
            for boat_i in range(6):
                if boat_i not in session_results: session_results[boat_i] = []
                rm = re.search(r'／(\d)', vals[boat_i])
                if rm: session_results[boat_i].append(int(rm.group(1)))

    for i in range(6):
        r = {"course": i+1}
        def gv(label, idx=i): return row_map.get(label, ["","","","","",""])[idx].strip() if label in row_map else ""

        r["name"] = gv("氏名")
        r["class"] = gv("級別") or "B1"
        age_s = gv("年齢").replace("歳","")
        r["age"] = int(age_s) if age_s.isdigit() else 35
        f_s = gv("F数").replace("F","")
        r["f_count"] = int(f_s) if f_s.isdigit() else 0
        nr_s = gv("勝率")
        r["national_rate"] = float(nr_s) if re.match(r'^\d+\.\d+$', nr_s) else 5.0
        r["local_rate"] = r["national_rate"]

        in_national = False; in_local = False
        nat_rate = None; loc_rate = None
        for tr in rows:
            cells = tr.find_all(["td","th"])
            texts2 = [c.get_text(strip=True) for c in cells]
            joined = " ".join(texts2)
            if "全国" in joined: in_national = True; in_local = False
            elif "当地" in joined: in_local = True; in_national = False
            elif "コース別" in joined: in_national = False; in_local = False

            if len(texts2) >= 7:
                data = texts2[-6:]
                label2 = " ".join(texts2[:-6]).strip()
                if "勝率" in label2:
                    val = data[i]
                    if re.match(r'^\d+\.\d+$', val):
                        if in_national and nat_rate is None: nat_rate = float(val)
                        elif in_local and loc_rate is None: loc_rate = float(val)

        if nat_rate is not None: r["national_rate"] = nat_rate
        if loc_rate is not None: r["local_rate"] = loc_rate

        in_motor = False; motor_2ren = 33.0
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
        st_s = gv("ST")
        r["avg_st"] = float(st_s) if re.match(r'^0\.\d+$', st_s) else 0.15

        in_course = False; course_ren3 = 0; course_win1 = 0; course_win2 = 0
        for tr in rows:
            cells = tr.find_all(["td","th"])
            texts2 = [c.get_text(strip=True) for c in cells]
            joined = " ".join(texts2)
            if "コース別" in joined: in_course = True
            elif "決り手" in joined or "モーター" in joined: in_course = False
            if in_course and len(texts2) >= 7:
                data = texts2[-6:]
                label2 = " ".join(texts2[:-6]).strip()
                val = data[i]
                if not re.match(r'^[\d.]+$', val): continue
                fval = float(val)
                if "1着率" in label2: course_win1 = fval
                elif "2着率" in label2: course_win2 = fval
                elif "3連率" in label2: course_ren3 = fval

        r["course_ren3"] = course_ren3
        r["course_win1"] = course_win1
        r["course_win2"] = course_win2

        in_kimarite = False
        kimarite_idx = 0
        km = {"nige": 0.0, "sashi": 0.0, "makuri": 0.0, "makurizashi": 0.0}
        
        for tr in rows:
            cells = tr.find_all(["td","th"])
            texts2 = [c.get_text(strip=True) for c in cells]
            joined = " ".join(texts2)
            
            if "決り手" in joined or "決まり手" in joined:
                in_kimarite = True
                kimarite_idx = 0
            elif "モーター" in joined and in_kimarite:
                in_kimarite = False
                
            if in_kimarite and len(texts2) >= 7:
                data = texts2[-6:]
                label2 = " ".join(texts2[:-6]).strip()
                val = str(data[i])
                m = re.search(r'([\d.]+)', val)
                fval = float(m.group(1)) if m else 0.0
                
                if "差" in label2 and ("まくり" in label2 or "捲" in label2) or kimarite_idx == 3:
                    km["makurizashi"] = fval
                elif "まくり" in label2 or "捲" in label2 or kimarite_idx == 2:
                    km["makuri"] = fval
                elif "差" in label2 or kimarite_idx == 1:
                    km["sashi"] = fval
                elif "逃" in label2 or "決" in label2 or kimarite_idx == 0:
                    km["nige"] = fval
                kimarite_idx += 1
                
        r["kimarite"] = km
        
        session_st = 0.15; session_ren2 = 0
        in_session = False
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
                if "ST" in label2 and re.match(r'^[\d.]+$', val): session_st = float(val)
                elif "2連率" in label2 and re.match(r'^[\d.]+$', val): session_ren2 = float(val)

        r["session_st"] = session_st
        r["session_ren2"] = session_ren2
        r["session_results"] = session_results.get(i, [])

        racers.append(r)
    return racers

# ━━━━━━━━━━━ 精密スコアリング ━━━━━━━━━━━
def calc_trend(results):
    s,n=0.0,[]
    if not results or len(results)<2: return 0,["⑨データ不足"]
    rec=list(reversed(results))
    if len(rec)>=2 and rec[0]==1 and rec[1]==1: s+=2.0; n.append("⑨連続1着+2")
    elif len(rec)>=2 and rec[0]<=2 and rec[1]<=2: s+=1.0; n.append("⑨連続2着内+1")
    if len(rec)>=3 and all(x>=4 for x in rec[:3]): s-=2.0; n.append("⑨3走着外-2")
    return round(s,1),n

def calc_scores(racers, jcd, weather, ex_times, is_final=False):
    venue_adj=IN_ADJ.get(jcd,0)
    ex_sorted=sorted(ex_times.items(),key=lambda x:x[1]) if ex_times else []
    ex_rank={c:r for r,(c,_) in enumerate(ex_sorted,1)}
    scored=[]
    for r in racers:
        c=r["course"]; sc={}; notes=[]
        s1={1:7,2:5,3:4,4:3.5,5:3,6:1.5}.get(c,3)
        if is_final and c==1: s1=12
        sc["①コース基礎"]=s1
        sc["②場別イン"]=venue_adj if c==1 else 0
        s3=0; ws=weather.get("wind_speed",0); wd=weather.get("wind_dir","")
        if "追い風" in wd and ws>=5:
            if c==1: s3-=2.5
            if c==2: s3+=1.5
        elif "向かい風" in wd and ws>=5:
            if c==1: s3-=2.5
            if c==4: s3+=1.5
        sc["③風速"]=s3
        mr=r.get("motor_2ren",33)
        sc["④モーター"]=3.0 if mr>50 else 1.5 if mr>=40 else 0.5 if mr>=30 else -2.0 if mr<25 else 0
        s5=0
        if c in ex_rank:
            rk=ex_rank[c]
            if rk==1 and len(ex_sorted)>1:
                d=ex_sorted[1][1]-ex_sorted[0][1]; s5=2.0 if d>=0.05 else 1.0 if d>=0.03 else 0
        sc["⑤展示"]=s5
        st_v=r.get("avg_st",0.15)
        sc["⑥ST"]=2.0 if st_v<=0.11 else 1.0 if st_v<=0.14 else -2.0 if st_v>=0.19 else 0
        sc["⑦F"]=-3.0 if r.get("f_count",0)>=2 else -1.0 if r.get("f_count",0)==1 else 0
        nr=r.get("national_rate",5.0)
        s8=3.5 if nr>=8 else 3.0 if nr>=7.5 else 2.0 if nr>=7 else 1.0 if nr>=6 else 0 if nr>=5 else -1.5
        sc["⑧勝率"]=s8
        s9,tn=calc_trend(r.get("session_results",[]))
        sc["⑨節間"]=s9
        
        km = r.get("kimarite", {})
        total_km = sum(km.values())
        if total_km > 0 and total_km <= 90: # Convert to pct
            nige_r = (km["nige"] / total_km) * 100
        else:
            nige_r = km["nige"]
            
        r["nige_pct"] = nige_r
        
        s15 = 0.0
        if c == 1:
            if nige_r >= 60: s15 = 3.0
            elif nige_r >= 40: s15 = 1.5
            elif nige_r > 0: s15 = -2.0
        sc["⑮決まり手"] = s15

        total=round(sum(sc.values()),1)
        scored.append({**r,"scores":sc,"total":total,"notes":notes})
    return sorted(scored,key=lambda x:x["total"],reverse=True)

# ━━━━━━━━━━━ UIコンポーネント ━━━━━━━━━━━
def bdg(c):
    css=COURSE_CSS.get(c,"background:#888;color:#FFF;")
    return f'<span style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:5px;font-weight:900;font-size:15px;{css}">{c}</span>'

def main():
    st.set_page_config(page_title="🚤 ボートレース予想AI",page_icon="🚤",layout="wide",initial_sidebar_state="collapsed")
    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap');
    .stApp{background:linear-gradient(135deg,#0a0a1a,#0d1b2a 40%,#1b2838);font-family:'Noto Sans JP',sans-serif}
    .hdr{background:linear-gradient(90deg,#E8212A,#B71C1C);padding:16px 24px;border-radius:12px;display:flex;align-items:center;gap:14px;box-shadow:0 4px 20px rgba(232,33,42,0.35);margin-bottom:16px}
    .hdr h1{color:#FFF!important;font-size:22px!important;font-weight:900!important;letter-spacing:3px;margin:0!important;padding:0!important}
    .hdr .sub{color:#ffcdd2;font-size:11px;letter-spacing:1px}
    .card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:16px;margin-bottom:12px}
    .sl{font-size:12px;font-weight:700;color:#E8212A;letter-spacing:2px;margin-bottom:8px}
    </style>""",unsafe_allow_html=True)
    st.markdown('<div class="hdr"><span style="font-size:32px">🚤</span><div><h1>BOAT RACE AI</h1><div class="sub">v4.9 ─ 抽出ロジック切り替え＆極限厳選システム</div></div></div>',unsafe_allow_html=True)

    # ━━━ ロジック選択 UI ━━━
    st.markdown('<div class="card"><div class="sl">🛠 狙い目フィルター設定</div>',unsafe_allow_html=True)
    target_logic = st.selectbox(
        "本日の抽出ロジックを選択してください:",
        [
            "【王道・超鉄板】1号艇の逃げ圧勝厳選（1-2-3 / 1-2-4）",
            "【中穴・ヒモ荒れ】イン逃げ＆外枠追走（1-4-全 / 1-5-全）",
            "【大穴・まくり】4カド一撃波乱（4-1-全 / 4-5-全）"
        ]
    )
    st.markdown('</div>',unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        sel_date=st.date_input("開催日",value=date.today(),label_visibility="collapsed")
        ds=sel_date.strftime("%Y-%m-%d")
    
    with st.spinner("🔍 開催場を取得中..."): venues=get_active_venues(ds)
    if not venues: st.warning("⚠️ 開催情報なし"); return

    # ━━━ 狙い目一括検索機能 ━━━
    if st.button(f"🔥 【{target_logic.split('】')[0].replace('【','')}】で全国検索を実行", type="primary", use_container_width=True):
        with st.spinner("全国のレースを解析中... (約1〜2分かかります)"):
            matches = []
            invested = 0
            returned = 0
            finished_count = 0
            
            for v in venues:
                jcd = v["jcd"]
                html = get_uchi_data(jcd, ds)
                if not html: continue
                rtimes = get_race_times(jcd, ds)
                
                for rno in range(1, 13):
                    racers = parse_uchi_race(html, rno)
                    if len(racers) < 6: continue
                    
                    before_info = get_before_info(jcd, ds, rno)
                    scored = calc_scores(racers, jcd, before_info.get("weather", {}), before_info.get("exhibition_times", {}))
                    if not scored or len(scored) < 3: continue
                    
                    top1 = scored[0]
                    top2 = scored[1]
                    top3 = scored[2]
                    score_dict = {r["course"]: r["total"] for r in scored}
                    
                    # ─── ロジック分岐 ───
                    buy_patterns = []
                    pred_str = ""
                    hit_invest = 0
                    
                    if "超鉄板" in target_logic:
                        # 厳選条件: 1位が1号艇。1号艇の勝率6.0以上。1位と2位のスコア差が3.0以上。
                        # かつ、2位と3位が「2号艇, 3号艇, 4号艇」のいずれか。
                        gap = top1["total"] - top2["total"]
                        if top1["course"] == 1 and top1["national_rate"] >= 6.0 and gap >= 3.0:
                            if top2["course"] in [2,3,4] and top3["course"] in [2,3,4]:
                                pred_str = "1-2-3 / 1-2-4 (2点買い)"
                                buy_patterns = [[1,2,3], [1,2,4]]
                                hit_invest = 200
                                
                    elif "中穴" in target_logic:
                        # 厳選条件: 1位が1号艇。2位か3位に「4号艇」か「5号艇」が入っている。
                        if top1["course"] == 1 and (top2["course"] in [4,5] or top3["course"] in [4,5]):
                            pred_str = "1-4-全 / 1-5-全 (8点買い)"
                            buy_patterns = [[1, 4, x] for x in range(2, 7) if x != 4] + \
                                           [[1, 5, x] for x in range(2, 7) if x != 5]
                            hit_invest = 800

                    elif "大穴" in target_logic:
                        # 厳選条件: 4号艇がAI1位。または4号艇のSTが内側(1,2,3)より0.02秒以上早い。
                        r4 = next((r for r in racers if r["course"]==4), None)
                        if r4:
                            st4 = r4["avg_st"]
                            st_diff = min(racers[0]["avg_st"], racers[1]["avg_st"], racers[2]["avg_st"]) - st4
                            if top1["course"] == 4 or (st4 <= 0.15 and st_diff >= 0.02):
                                pred_str = "4-1-全 / 4-5-全 (8点買い)"
                                buy_patterns = [[4, 1, x] for x in range(2, 7) if x != 1] + \
                                               [[4, 5, x] for x in range(1, 7) if x != 5]
                                hit_invest = 800

                    # 条件に合致した場合のみ登録
                    if buy_patterns:
                        race_info = {
                            "jcd": jcd, "name": v["name"], "rno": rno,
                            "time": rtimes.get(rno, "--:--"),
                            "pred_str": pred_str,
                            "is_finished": False,
                            "hit": False,
                            "sanrentan": "未確定",
                            "payout": 0
                        }
                        
                        res = get_official_result(jcd, ds, rno)
                        if res:
                            race_info["is_finished"] = True
                            race_info["sanrentan"] = res["sanrentan"]
                            finished_count += 1
                            invested += hit_invest
                            
                            if res["ranks"] in buy_patterns:
                                race_info["hit"] = True
                                race_info["payout"] = res["payout"]
                                returned += res["payout"]
                                
                        matches.append(race_info)
                        
            st.session_state["search_matches"] = matches
            st.session_state["search_invested"] = invested
            st.session_state["search_returned"] = returned
            st.session_state["search_finished"] = finished_count
            st.session_state["search_done"] = True

    # ━━━ 検索結果ダッシュボード ━━━
    if st.session_state.get("search_done"):
        matches = st.session_state.get("search_matches", [])
        inv = st.session_state.get("search_invested", 0)
        ret = st.session_state.get("search_returned", 0)
        fin = st.session_state.get("search_finished", 0)
        roi = (ret / inv * 100) if inv > 0 else 0
        
        st.markdown('<div style="background:rgba(232, 33, 42, 0.1); padding:16px; border-radius:12px; border:1px solid #E8212A; margin-bottom:16px;">', unsafe_allow_html=True)
        st.markdown(f"<h3 style='margin-bottom:4px;'>🎯 抽出結果 : 計 {len(matches)} 件</h3>", unsafe_allow_html=True)
        
        roi_color = "#2D8C3C" if roi >= 100 else "#E8212A" if roi > 0 else "#fff"
        dash_html = (
            f"<div style='display:flex; justify-content:space-around; background:rgba(0,0,0,0.3); padding:16px; border-radius:8px; margin-top:12px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.1);'>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>終了済レース</span><br><span style='font-size:22px;font-weight:bold;'>{fin} <span style='font-size:14px;'>件</span></span></div>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>合計投資</span><br><span style='font-size:22px;font-weight:bold;'>{inv} <span style='font-size:14px;'>円</span></span></div>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>払戻合計</span><br><span style='font-size:22px;font-weight:bold;color:{roi_color};'>{ret} <span style='font-size:14px;'>円</span></span></div>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>本日の回収率</span><br><span style='font-size:24px;font-weight:900;color:{roi_color};'>{roi:.1f} <span style='font-size:16px;'>%</span></span></div>"
            f"</div>"
        )
        st.markdown(dash_html, unsafe_allow_html=True)

        if matches:
            for m in matches:
                bg_color = "rgba(45, 140, 60, 0.2)" if m["hit"] else "rgba(255,255,255,0.03)"
                border = "border:1px solid #2D8C3C;" if m["hit"] else "border:1px solid rgba(255,255,255,0.1);"
                hit_badge = "<span style='background:#2D8C3C; color:#fff; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:bold;'>的中🎯</span>" if m["hit"] else ""
                
                card_html = (
                    f"<div style='background:{bg_color}; padding:12px 16px; border-radius:8px; {border} margin-bottom:10px;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>"
                    f"<div><span style='color:#E8212A;font-weight:bold;font-size:16px;'>{m['name']} {m['rno']}R</span>"
                    f"<span style='color:#ccc; font-size:13px; margin-left:8px;'>🕒 {m['time']}</span></div>"
                    f"{hit_badge}</div>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; font-size:15px; padding-top:4px; border-top:1px dashed rgba(255,255,255,0.1);'>"
                    f"<div style='color:#F5C518;'><span style='font-size:12px; color:#aaa;'>買い目:</span> "
                    f"<span style='font-weight:900; font-size:18px; letter-spacing:1px;'>{m['pred_str']}</span></div>"
                    f"<div style='text-align:right;'><span style='font-size:12px; color:#aaa;'>3連単結果:</span> "
                    f"<span style='font-weight:bold;'>{m['sanrentan']}</span></div>"
                    f"</div></div>"
                )
                st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning("現在、選択した条件に合致する厳選レースは見つかりませんでした。別のロジックをお試しください。")
            
        if st.button("✖ 検索結果を閉じる", key="close_search"):
            st.session_state["search_done"] = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # ━━━ 個別レース解析UI（従来通り） ━━━
    st.markdown('<div class="card"><div class="sl">個別レース解析</div>',unsafe_allow_html=True)
    nc=min(len(venues),4); cols=st.columns(nc)
    for i,v in enumerate(venues):
        with cols[i%nc]:
            if st.button(f"🏟️{v['name']}",key=f"v{v['jcd']}",use_container_width=True):
                st.session_state["venue"]=v["jcd"]; st.session_state.pop("race",None); st.rerun()
    st.markdown('</div>',unsafe_allow_html=True)
    
    sv=st.session_state.get("venue")
    if sv:
        rtimes=get_race_times(sv,ds)
        for row_start in [1,7]:
            rc=st.columns(6)
            for i in range(6):
                rno=row_start+i
                with rc[i]:
                    t=rtimes.get(rno,"")
                    lbl=f"{rno}R\\n{t}" if t else f"{rno}R"
                    if st.button(lbl,key=f"r{rno}",use_container_width=True): 
                        st.session_state["race"]=rno; st.rerun()
        
        sr=st.session_state.get("race")
        if sr:
            st.divider(); st.subheader(f"🏁 {VENUES[sv]} {sr}R 個別解析")
            # --- 簡易描画 ---
            uchi_html = get_uchi_data(sv, ds)
            racers = parse_uchi_race(uchi_html, sr) if uchi_html else []
            before = get_before_info(sv, ds, sr)
            if racers:
                scored=calc_scores(racers,sv,before.get("weather",{}),before.get("exhibition_times",{}))
                for idx,r in enumerate(scored):
                    crown="👑 " if idx==0 else ""; bg="rgba(245,197,24,0.06)" if idx==0 else "transparent"
                    st.markdown(f'<div style="display:flex;align-items:center;gap:8px;padding:6px;background:{bg};border-radius:8px;margin-bottom:4px">{bdg(r["course"])}<div style="font-weight:700;">{crown}{r.get("name","")}</div><div>{r["total"]} pt</div></div>',unsafe_allow_html=True)

if __name__=="__main__":
    main()
