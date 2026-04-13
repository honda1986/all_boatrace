"""
🚤 ボートレース予想アプリ v3.9 (UI表示崩れ修正＆通信安定化版)
━━━━━━━━━━━━━━━━━━━━━━━━
データソース: uchisankaku.sakura.ne.jp（コース別・節間・全選手データ）
             boatrace.jp（開催場一覧・直前情報・レース結果）
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
    r.encoding = "utf-8" # 文字化けとタイムアウト防止のため明示的に指定
    return r.text

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
    except Exception as e:
        st.error(f"開催場取得失敗: {e}"); return []

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

# ━━━━━━━━━━━ uchisankaku(メインデータ) ━━━━━━━━━━━
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
        def gv(label, idx=i):
            return row_map.get(label, ["","","","","",""])[idx].strip() if label in row_map else ""

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

        in_session = False; session_st = 0.15; session_ren2 = 0; session_rank = 0; session_pts = 0
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

# ━━━━━━━━━━━ スコアリング ━━━━━━━━━━━
def calc_trend(results):
    s,n=0.0,[]
    if not results or len(results)<2: return 0,["⑨データ不足"]
    rec=list(reversed(results))
    if len(rec)>=2 and rec[0]==1 and rec[1]==1: s+=2.0; n.append("⑨連続1着+2")
    elif len(rec)>=2 and rec[0]<=2 and rec[1]<=2: s+=1.0; n.append("⑨連続2着内+1")
    if len(rec)>=3 and rec[2]>rec[1]>rec[0]: s+=1.5; n.append("⑨3走改善+1.5")
    if len(rec)>=3 and all(x>=4 for x in rec[:3]): s-=2.0; n.append("⑨3走着外-2")
    if rec[0]==6: s-=1.5; n.append("⑨直近6着-1.5")
    if len(rec)>=3:
        r2=sum(1 for x in rec if x<=2)/len(rec)*100
        if r2>=60: s+=1.0; n.append(f"⑨2連率{r2:.0f}%+1")
        elif r2<=15: s-=1.0; n.append(f"⑨2連率{r2:.0f}%-1")
    return round(s,1),n

def calc_c13(course, win1, ren3):
    s,n=0.0,[]
    if ren3<=0 and win1<=0: return 0,["⑬データなし"]
    avg_w=NAT_WIN1.get(course,10); avg_r=NAT_REN3.get(course,50)
    dw=win1-avg_w
    if dw>=10: s+=3.0; n.append(f"⑬巧者(1着率{win1:.1f}%+{dw:.0f})")
    elif dw>=5: s+=1.5; n.append(f"⑬得意(1着率{win1:.1f}%)")
    elif dw<=-10: s-=2.5; n.append(f"⑬苦手(1着率{win1:.1f}%)")
    elif dw<=-5: s-=1.0; n.append(f"⑬やや苦手(1着率{win1:.1f}%)")
    dr=ren3-avg_r
    if dr>=10: s+=1.5; n.append(f"⑬3連率安定({ren3:.0f}%)")
    elif dr<=-10: s-=1.0; n.append(f"⑬3連率不足({ren3:.0f}%)")
    if course==1 and win1>=70: s+=1.0; n.append("⑬イン巧者+1")
    if course>=4 and avg_w>0 and win1>=avg_w*2: s+=1.5; n.append("⑬まくり屋+1.5")
    return round(s,1),n

def calc_scores(racers, jcd, weather, ex_times, is_final=False):
    venue_adj=IN_ADJ.get(jcd,0); is_rough=jcd in ROUGH
    ex_sorted=sorted(ex_times.items(),key=lambda x:x[1]) if ex_times else []
    ex_rank={c:r for r,(c,_) in enumerate(ex_sorted,1)}
    scored=[]
    for r in racers:
        c=r["course"]; sc={}; notes=[]
        s1={1:7,2:5,3:4,4:3.5,5:3,6:1.5}.get(c,3)
        if is_final and c==1: s1=12; notes.append("優勝戦1C")
        sc["①コース基礎"]=s1
        sc["②場別イン"]=venue_adj if c==1 else 0
        s3=0; ws=weather.get("wind_speed",0); wd=weather.get("wind_dir",""); wv=weather.get("wave",0)
        if "追い風" in wd and ws>=5:
            if c==1: s3-=2.5
            if c==2: s3+=1.5
        elif "追い風" in wd and 3<=ws<=4:
            if c==1: s3-=1.0
            if c==3: s3+=0.5
        elif "向かい風" in wd and ws>=5:
            if c==1: s3-=2.5
            if c==4: s3+=1.5
        if wv>=8 and c==1: s3-=3.0; notes.append("高波")
        sc["③風速波高"]=s3
        mr=r.get("motor_2ren",33)
        sc["④モーター"]=3.0 if mr>50 else 1.5 if mr>=40 else 0.5 if mr>=30 else -2.0 if mr<25 else 0
        s5=0
        if c in ex_rank:
            rk=ex_rank[c]
            if rk==1 and len(ex_sorted)>1:
                d=ex_sorted[1][1]-ex_sorted[0][1]; s5=2.0 if d>=0.07 else 1.0 if d>=0.04 else 0
            if rk==6: s5=-3.0 if c==1 else -2.0
        sc["⑤展示タイム"]=s5
        st_v=r.get("avg_st",0.15)
        sc["⑥平均ST"]=2.0 if st_v<=0.10 else 1.0 if st_v<=0.13 else -2.0 if st_v>=0.20 else -1.0 if st_v>=0.17 else 0
        fc=r.get("f_count",0)
        sc["⑦Fペナ"]=-3.0 if fc>=2 else (-2.0 if c>=4 else -1.0) if fc==1 else 0
        nr=r.get("national_rate",5.0)
        s8=3.5 if nr>=8 else 3.0 if nr>=7.5 else 2.0 if nr>=7 else 1.0 if nr>=6 else 0 if nr>=5 else -1.0 if nr>=4 else -2.0
        if is_rough and r.get("local_rate",5.0)>=nr+0.5: s8+=1.0; notes.append("難水面+1")
        sc["⑧選手力"]=s8
        s9,tn=calc_trend(r.get("session_results",[]))
        notes.extend(tn); sc["⑨節間動態"]=s9
        sc["⑩進入変動"]=0
        sc["⑪クラス"]={"A1":2.5,"A2":1.0,"B1":0,"B2":-2.0}.get(r.get("class","B1"),0)
        age=r.get("age",30); cr=r.get("class","B1")
        s12=1.0 if 25<=age<=35 else 0.5 if 36<=age<=44 else 0 if 45<=age<=50 else -0.5 if age>=51 else -0.5 if age<=24 else 0
        if cr=="A1" and age>=50 and s12<0: s12=0; notes.append("A1ベテラン")
        sc["⑫年齢"]=s12
        s13,cn=calc_c13(c, r.get("course_win1",0), r.get("course_ren3",0))
        notes.extend(cn); sc["⑬コース別"]=s13
        lr=r.get("local_rate",5.0)
        s14=2.0 if lr>=nr+1.0 else 1.0 if lr>=nr+0.5 else -1.5 if lr<=nr-1.0 else -0.5 if lr<=nr-0.5 else 0
        if c==1 and lr>=6.5: s14+=1.5; notes.append("当地6.5↑+1.5")
        sc["⑭当地"]=s14
        total=round(sum(sc.values()),1)
        scored.append({**r,"scores":sc,"total":total,"notes":notes})
    return sorted(scored,key=lambda x:x["total"],reverse=True)

# ━━━━━━━━━━━ 買い目 ━━━━━━━━━━━
def gen_scenario(scored,weather):
    by_c={r["course"]:r for r in scored}
    top=scored[0]; sec=scored[1] if len(scored)>1 else None
    gap=round(top["total"]-sec["total"],1) if sec else 99
    tc=top["course"]
    if tc==1: pat="逃げ"; txt=f"1C{top.get('name','')}イン逃げ本線。"
    elif tc==2: pat="差し"; txt=f"2C{top.get('name','')}差し展開。"
    elif tc==3: pat="まくり差し"; txt=f"3C{top.get('name','')}まくり差し。"
    else: pat="まくり"; txt=f"{tc}C{top.get('name','')}外まくり。"
    ws=weather.get("wind_speed",0); wd=weather.get("wind_dir","")
    if ws>=5: txt+=f" {wd}{ws}m影響大。"
    if gap>=4: fr,conf=0.60,"高"
    elif gap>=2: fr,conf=0.45,"中"
    elif gap>=1: fr,conf=0.33,"低"
    else: fr,conf=0.25,"極低"
    p2={};
    if pat=="逃げ": p2={2:0.34,3:0.27}
    elif pat=="差し": p2={1:0.60,3:0.15}
    elif pat=="まくり差し": p2={1:0.55,2:0.15}
    elif pat=="まくり": o=min(tc+1,6); p2={1:0.30,o:0.40}
    s2={}
    for r in scored:
        cc=r["course"]
        if cc==tc: continue
        base=p2.get(cc,0.05); ri=scored.index(r)
        mult=1.3 if ri<=1 else 1.1 if ri<=2 else 0.6 if ri>=4 else 0.9
        s2[cc]=round(base*mult,4)
    ss=sum(s2.values())
    if ss>0: s2={k:round(v/ss,4) for k,v in s2.items()}
    if gap<1: rtype="見送り"; reason=f"スコア差{gap}pt→完全混戦"; fms=[]; bt=""
    elif gap<2:
        rtype="注意"; reason=f"スコア差{gap}pt→混戦・穴検討"
        fms=[f"{tc}-{scored[1]['course']}-全",f"{scored[1]['course']}-{tc}-全"]; bt="3連単(穴型)"
    else:
        rtype="買い"; reason=f"スコア差{gap}pt→{top.get('name','')}({tc}C)有力"
        t2=sorted(s2.items(),key=lambda x:x[1],reverse=True)[:2]
        fms=[f"{tc}-{'/'.join(str(x[0]) for x in t2)}-全"]; bt="3連単(基本型)"
    bets=[]
    if rtype!="見送り":
        firsts=[(tc,fr)]
        if rtype=="注意": firsts.append((scored[1]["course"],1.0-fr))
        for fc,f_r in firsts:
            s2c=sorted([(r["course"],s2.get(r["course"],0.05)) for r in scored if r["course"]!=fc],key=lambda x:x[1],reverse=True)[:3]
            for sc_c,sr in s2c:
                rem=[r for r in scored if r["course"] not in (fc,sc_c)]
                tots=[max(r2["total"]+26.5,0.5) for r2 in rem]; ts=sum(tots)
                for tr in rem[:3]:
                    t_r=next((tots[j]/ts for j,r2 in enumerate(rem) if r2["course"]==tr["course"]),0.25) if ts>0 else 0.25
                    hit=round(f_r*sr*t_r,5)
                    if hit>0.001:
                        lbl="◎本命" if hit>=0.08 else "○対抗" if hit>=0.04 else "▲連下" if hit>=0.02 else "△押さえ"
                        bets.append({"bet":f"{fc}-{sc_c}-{tr['course']}","hit":hit,"odds":round(1/hit,1),"lbl":lbl})
    seen=set(); ub=[]
    for b in sorted(bets,key=lambda x:x["hit"],reverse=True):
        if b["bet"] not in seen: seen.add(b["bet"]); ub.append(b)
    return {"scenario":txt,"pattern":pat,"rec_type":rtype,"reason":reason,"fms":fms,"bt":bt,"bets":ub[:12],"gap":gap,"conf":conf}

# ━━━━━━━━━━━ 表示 ━━━━━━━━━━━
def bdg(c):
    css=COURSE_CSS.get(c,"background:#888;color:#FFF;")
    return f'<span style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:5px;font-weight:900;font-size:15px;{css}">{c}</span>'

def sbar(score):
    rng=62; pct=max(0,min(100,(score+26)/rng*100)); zp=26/rng*100
    clr="#E8212A" if score>=20 else "#F5C518" if score>=12 else "#1B6DB5" if score>=5 else "#888"
    left=zp if score>=0 else pct; w=abs(pct-zp)
    return f'<div style="height:20px;background:#1a1a2e;border-radius:10px;position:relative;overflow:hidden"><div style="height:16px;border-radius:8px;margin-top:2px;margin-left:{left}%;width:{w}%;background:linear-gradient(90deg,{clr}CC,{clr})"></div><span style="position:absolute;right:8px;top:0;line-height:20px;font-size:12px;font-weight:800;color:#FFF;text-shadow:0 1px 3px rgba(0,0,0,0.8)">{score:.1f}</span></div>'

# ━━━━━━━━━━━ メイン ━━━━━━━━━━━
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
    div[data-testid="stMetric"]{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px}
    </style>""",unsafe_allow_html=True)
    st.markdown('<div class="hdr"><span style="font-size:32px">🚤</span><div><h1>BOAT RACE AI</h1><div class="sub">v3.9 ─ 1-2-3/1-2-4 鉄板検索＆UI修正版</div></div></div>',unsafe_allow_html=True)

    # STEP1
    st.markdown('<div class="card"><div class="sl">STEP 1 ─ 開催日</div>',unsafe_allow_html=True)
    sel_date=st.date_input("日付",value=date.today(),label_visibility="collapsed")
    ds=sel_date.strftime("%Y-%m-%d")
    st.markdown('</div>',unsafe_allow_html=True)

    # STEP2
    st.markdown('<div class="card"><div class="sl">STEP 2 ─ 開催場</div>',unsafe_allow_html=True)
    with st.spinner("🔍 開催場を取得中..."): venues=get_active_venues(ds)
    if not venues: st.warning("⚠️ 開催情報なし"); st.markdown('</div>',unsafe_allow_html=True); return

    # ━━━ 追加機能: 1-2鉄板レース 一括検索（スコア順位＆回収率） ━━━
    if st.button("🔥 全場検索（スコア上位が 1-2-3 / 1-2-4 のレースのみ）", type="primary", use_container_width=True):
        with st.spinner("全国の全レースをスコアリングして抽出中... (約1〜2分かかります)"):
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
                    scored = calc_scores(
                        racers, jcd, 
                        before_info.get("weather", {}), 
                        before_info.get("exhibition_times", {}), 
                        is_final=(rno==12)
                    )
                    
                    if not scored or len(scored) < 3: continue
                    
                    top1 = scored[0]["course"]
                    top2 = scored[1]["course"]
                    top3 = scored[2]["course"]
                    
                    if top1 == 1 and top2 == 2 and top3 in [3, 4]:
                        ai_pred = [top1, top2, top3]
                        pred_str = "-".join(map(str, ai_pred))
                        
                        race_info = {
                            "jcd": jcd, "name": v["name"], "rno": rno,
                            "time": rtimes.get(rno, "--:--"),
                            "pred": ai_pred,
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
                            invested += 100 
                            
                            if res["ranks"] == ai_pred:
                                race_info["hit"] = True
                                race_info["payout"] = res["payout"]
                                returned += res["payout"]
                                
                        matches.append(race_info)
                        
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
        st.markdown(f"<h3 style='margin-bottom:4px;'>🎯 狙い目レース : 計 {len(matches)} 件</h3>", unsafe_allow_html=True)
        st.caption("抽出条件: 全レースをスコアリングし、1位=1号艇, 2位=2号艇, 3位=3or4号艇 になったレースのみ表示")
        
        roi_color = "#2D8C3C" if roi >= 100 else "#E8212A" if roi > 0 else "#fff"
        
        # HTMLの字下げをなくし、1行の文字列として結合（Markdownコードブロック化を防止）
        dash_html = (
            f"<div style='display:flex; justify-content:space-around; background:rgba(0,0,0,0.3); padding:16px; border-radius:8px; margin-top:12px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.1);'>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>終了済レース</span><br><span style='font-size:22px;font-weight:bold;'>{fin} <span style='font-size:14px;'>件</span></span></div>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>投資 (1点100円)</span><br><span style='font-size:22px;font-weight:bold;'>{inv} <span style='font-size:14px;'>円</span></span></div>"
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
                
                # 同様に字下げをなくして結合
                card_html = (
                    f"<div style='background:{bg_color}; padding:12px 16px; border-radius:8px; {border} margin-bottom:10px;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>"
                    f"<div><span style='color:#E8212A;font-weight:bold;font-size:16px;'>{m['name']} {m['rno']}R</span>"
                    f"<span style='color:#ccc; font-size:13px; margin-left:8px;'>🕒 {m['time']}</span></div>"
                    f"{hit_badge}</div>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; font-size:15px; padding-top:4px; border-top:1px dashed rgba(255,255,255,0.1);'>"
                    f"<div style='color:#F5C518;'><span style='font-size:12px; color:#aaa;'>AIスコア上位:</span> "
                    f"<span style='font-weight:900; font-size:18px; letter-spacing:1px;'>{m['pred_str']}</span></div>"
                    f"<div style='text-align:right;'><span style='font-size:12px; color:#aaa;'>3連単結果:</span> "
                    f"<span style='font-weight:bold;'>{m['sanrentan']}</span></div>"
                    f"</div></div>"
                )
                st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning("現在、全レースの中にスコア上位が 1-2-3 または 1-2-4 になるレースは見つかりませんでした。")
            
        if st.button("✖ 検索結果を閉じる", key="close_search"):
            st.session_state["search_done"] = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    st.success(f"📍 {len(venues)}場開催中")
    nc=min(len(venues),4); cols=st.columns(nc)
    for i,v in enumerate(venues):
        with cols[i%nc]:
            adj=f" 🟢+{v['in_adj']}" if v["in_adj"]>0 else f" 🟠{v['in_adj']}" if v["in_adj"]<0 else ""
            if st.button(f"🏟️{v['name']}{adj}",key=f"v{v['jcd']}",use_container_width=True):
                st.session_state["venue"]=v["jcd"]; st.session_state.pop("race",None); st.rerun()
    st.markdown('</div>',unsafe_allow_html=True)
    sv=st.session_state.get("venue")
    if not sv: return

    # STEP3
    st.markdown(f'<div class="card"><div class="sl">STEP 3 ─ {VENUES[sv]} レース選択 (詳細解析)</div>',unsafe_allow_html=True)
    rtimes=get_race_times(sv,ds)
    for row_start in [1,7]:
        rc=st.columns(6)
        for i in range(6):
            rno=row_start+i
            with rc[i]:
                t=rtimes.get(rno,""); pre="🏆" if rno==12 else ""
                lbl=f"{pre}{rno}R\n{t}" if t else f"{pre}{rno}R"
                if st.button(lbl,key=f"r{rno}",use_container_width=True): 
                    st.session_state["race"]=rno; st.rerun()
    st.markdown('</div>',unsafe_allow_html=True)
    sr=st.session_state.get("race")
    if not sr: return

    # ━━━ 通常の解析表示（画面下部） ━━━
    st.divider(); st.subheader(f"🏁 {VENUES[sv]} {sr}R 解析")

    with st.spinner("📊 データ取得中..."):
        uchi_html = get_uchi_data(sv, ds)
        racers = parse_uchi_race(uchi_html, sr) if uchi_html else []
        before = get_before_info(sv, ds, sr)
        race_result = get_official_result(sv, ds, sr)

    if race_result:
        st.success("🏁 **このレースは終了しています**")
        s_text = race_result.get("sanrentan", "データなし")
        st.metric("💰 3連単 払戻金", s_text)
        st.divider()

    if not racers:
        st.error("❌ 出走データ取得失敗。uchisankakuにデータがないか、中止になった可能性があります。")
        return

    scored=calc_scores(racers,sv,before.get("weather",{}),before.get("exhibition_times",{}),is_final=(sr==12))
    analysis=gen_scenario(scored,before.get("weather",{}))

    w=before.get("weather",{})
    wp=[]
    if w.get("wind_dir"): wp.append(w["wind_dir"])
    if w.get("wind_speed"): wp.append(f"{w['wind_speed']}m")
    if w.get("wave"): wp.append(f"波高{w['wave']}cm")
    if wp: st.info(f"🌊 気象: {' / '.join(wp)}")

    st.markdown("#### 📊 全艇スコア一覧")
    for idx,r in enumerate(scored):
        crown="👑 " if idx==0 else ""; bg="rgba(245,197,24,0.06)" if idx==0 else "transparent"; nc2="#F5C518" if idx==0 else "#ddd"
        st.markdown(f'<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:{bg};border-radius:8px;margin-bottom:4px">{bdg(r["course"])}<div style="min-width:80px;font-weight:700;font-size:14px;color:{nc2}">{crown}{r.get("name","")}</div><div style="min-width:60px;font-size:11px;color:#888">{r.get("class","")}/{r.get("national_rate",0)}</div><div style="flex:1">{sbar(r["total"])}</div></div>',unsafe_allow_html=True)

    with st.expander("📋 スコア内訳"):
        rows=[{"コース":f'{r["course"]}C',"選手":r.get("name",""),"合計":r["total"],**r["scores"]} for r in scored]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

    st.markdown("#### 🌊 展開シナリオ")
    st.write(analysis["scenario"])
    top3=" / ".join([f"**{'本命' if i==0 else '対抗' if i==1 else '3番手'}**:{r['course']}C{r.get('name','')}({r['total']}pt)" for i,r in enumerate(scored[:3])])
    st.write(top3)
    c1,c2=st.columns(2)
    with c1: st.metric("決まり手予測",analysis["pattern"])
    with c2: st.metric("信頼度",analysis["conf"])

    st.markdown("#### 🎯 推奨判定")
    rt=analysis["rec_type"]
    if rt=="見送り": st.warning(f"⚠️ **{rt}**\n\n{analysis['reason']}")
    elif rt=="注意": st.info(f"⚡ **{rt}**\n\n{analysis['reason']}")
    else: st.success(f"🎯 **{rt}**\n\n{analysis['reason']}")

    st.markdown("---")
    st.caption("※AI予想は参考情報です。購入は自己判断・自己責任で。\n※データ:uchisankaku.sakura.ne.jp / boatrace.jp")

if __name__=="__main__":
    main()
