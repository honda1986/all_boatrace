"""
🚤 ボートレース予想アプリ v5.0 (多角的スコアリング強襲版)
━━━━━━━━━━━━━━━━━━━━━━━━
データソース: uchisankaku.sakura.ne.jp（コース別・節間・全選手データ・決まり手）
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
    r.encoding = "utf-8"
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

        # ── 決まり手パース ──
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
    st.markdown('<div class="hdr"><span style="font-size:32px">🚤</span><div><h1>BOAT RACE AI</h1><div class="sub">v5.0 ─ 多角的スコアリング強襲ハンター</div></div></div>',unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="sl">STEP 1 ─ 開催日</div>',unsafe_allow_html=True)
    sel_date=st.date_input("日付",value=date.today(),label_visibility="collapsed")
    ds=sel_date.strftime("%Y-%m-%d")
    st.markdown('</div>',unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="sl">STEP 2 ─ 開催場</div>',unsafe_allow_html=True)
    with st.spinner("🔍 開催場を取得中..."): venues=get_active_venues(ds)
    if not venues: st.warning("⚠️ 開催情報なし"); st.markdown('</div>',unsafe_allow_html=True); return

    # ━━━ 多角的スコアリング強襲検索 ━━━
    EXCLUDE_BETS = [[1,2,3],[1,3,2]]

    def get_eff_st(r):
        """節間ST優先、未走なら平均ST"""
        s = r.get("session_st", 0)
        if s and s > 0 and s != 0.15 and r.get("session_results"):
            return s
        return r.get("avg_st", 0.15)

    def evaluate_attack(racers, atk_c):
        """攻め艇(atk_c=3〜6)の強襲スコアを多角的に算出。不成立ならNone"""
        atk = racers[atk_c - 1]
        atk_st = get_eff_st(atk)
        if atk_st > 0.19: return None  # 攻め艇自体が遅すぎ

        inner_sts = [get_eff_st(racers[j]) for j in range(atk_c - 1)]
        if not inner_sts: return None

        avg_inner = sum(inner_sts) / len(inner_sts)
        st_diff = avg_inner - atk_st  # ＋なら攻め艇が早い

        # ── 最低条件: 内側平均より0.02秒以上早い ──
        if st_diff < 0.02: return None

        score = 0.0
        reasons = []

        # ① ST差（最重要）
        if st_diff >= 0.06:
            score += 6; reasons.append(f"ST差極大+{st_diff:.2f}")
        elif st_diff >= 0.04:
            score += 4; reasons.append(f"ST差大+{st_diff:.2f}")
        elif st_diff >= 0.03:
            score += 3; reasons.append(f"ST差+{st_diff:.2f}")
        else:
            score += 1.5

        # 攻め艇の絶対ST
        if atk_st <= 0.11:
            score += 2.5; reasons.append(f"攻ST◎{atk_st:.2f}")
        elif atk_st <= 0.14:
            score += 1.5
        elif atk_st <= 0.16:
            score += 0.5

        # ② モーター2連率（攻め艇）
        m2 = atk.get("motor_2ren", 33)
        if m2 >= 50:
            score += 3; reasons.append(f"機力◎{m2:.0f}%")
        elif m2 >= 40:
            score += 1.5
        elif m2 >= 30:
            pass
        elif m2 < 25:
            score -= 2; reasons.append(f"機力✕{m2:.0f}%")

        # ③ 選手勝率（攻め艇）
        nr = atk.get("national_rate", 5.0)
        if nr >= 7.5:
            score += 3; reasons.append(f"勝率{nr:.2f}")
        elif nr >= 7.0:
            score += 2
        elif nr >= 6.0:
            score += 1
        elif nr < 5.0:
            score -= 1.5

        # ④ 級別
        cls = atk.get("class", "B1")
        if cls == "A1":
            score += 2; reasons.append("A1")
        elif cls == "A2":
            score += 1
        elif cls == "B2":
            score -= 2; reasons.append("B2注意")

        # ⑤ 決まり手傾向（まくり+まくり差し）
        km = atk.get("kimarite", {})
        mak_total = km.get("makuri", 0) + km.get("makurizashi", 0)
        if mak_total >= 40:
            score += 3; reasons.append(f"まくり系{mak_total:.0f}%")
        elif mak_total >= 25:
            score += 1.5
        elif mak_total < 10 and atk_c >= 4:
            score -= 1

        # ⑥ 壁の弱さ（内側艇のモーター・選手力が弱いほどチャンス）
        wall_weak = 0
        for j in range(atk_c - 1):
            inn = racers[j]
            if inn.get("motor_2ren", 33) < 28: wall_weak += 1
            if inn.get("national_rate", 5.0) < 4.5: wall_weak += 1
            cls_i = inn.get("class", "B1")
            if cls_i == "B2": wall_weak += 1
        if wall_weak >= 3:
            score += 2.5; reasons.append("壁弱い")
        elif wall_weak >= 2:
            score += 1.5
        elif wall_weak >= 1:
            score += 0.5

        # ⑦ 節間動態（攻め艇の今節調子）
        sr = atk.get("session_results", [])
        if len(sr) >= 2:
            if sr[-1] <= 2 and sr[-2] <= 2:
                score += 2; reasons.append("今節好調")
            elif all(r >= 5 for r in sr[-2:]):
                score -= 1.5

        # ⑧ F持ち減算
        fc = atk.get("f_count", 0)
        if fc >= 2:
            score -= 3; reasons.append("F2持ち")
        elif fc == 1:
            score -= 1.5

        # ── 外コース(5C/6C)はST差が大きくないと厳しい ──
        if atk_c >= 5 and st_diff < 0.04:
            return None  # 外からのまくりはST差必須
        if atk_c == 6 and score < 8:
            return None  # 6Cは高スコアのみ通す

        # ── 最低スコア閾値 ──
        if score < 5: return None

        # 信頼度ランク
        if score >= 14: stars = "★★★"
        elif score >= 10: stars = "★★☆"
        elif score >= 7: stars = "★☆☆"
        else: stars = "☆☆☆"

        return {
            "score": round(score, 1),
            "stars": stars,
            "reasons": reasons,
            "atk_st": atk_st,
            "st_diff": st_diff,
        }

    def make_buy_patterns(atk_c, racers):
        """攻め艇コースから買い目を生成（1-2-3/1-3-2除外）"""
        patterns = []
        # 1着=攻め艇、2着候補を選定
        second_candidates = []
        if atk_c == 3:
            second_candidates = [1, 4, 2]  # まくり→1号艇残り、差し展開
        elif atk_c == 4:
            second_candidates = [1, 5, 3]  # カドまくり→1号艇残り、外伸び
        elif atk_c == 5:
            second_candidates = [4, 1, 6]
        elif atk_c == 6:
            second_candidates = [5, 1, 4]

        for s in second_candidates:
            for t in range(1, 7):
                if t != atk_c and t != s:
                    bet = [atk_c, s, t]
                    if bet not in EXCLUDE_BETS:
                        patterns.append(bet)

        # 表示用文字列
        sec_str = "/".join(str(s) for s in second_candidates)
        n = len(patterns)
        pred_str = f"{atk_c}-[{sec_str}]-全 ({n}点)"
        return patterns, pred_str

    if st.button("🔥 狙い目検索（多角的スコアリング / 3〜6コース強襲）", type="primary", use_container_width=True):
        with st.spinner("全国のレースを多角的に解析中... (約1〜2分)"):
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

                    # 3C〜6Cの全コースを評価し、最高スコアを採用
                    best = None
                    best_c = 0
                    for c in [3, 4, 5, 6]:
                        ev = evaluate_attack(racers, c)
                        if ev and (best is None or ev["score"] > best["score"]):
                            best = ev
                            best_c = c

                    if not best: continue

                    buy_patterns, pred_str = make_buy_patterns(best_c, racers)
                    n_bets = len(buy_patterns)

                    # ST一覧
                    st_vals = [get_eff_st(racers[k]) for k in range(6)]
                    st_info = " ".join(f"{k+1}C({st_vals[k]:.2f})" for k in range(6))
                    # 節間/平均どちらを使ったか表示
                    st_src = "節間ST" if racers[best_c-1].get("session_results") and racers[best_c-1].get("session_st",0) != 0.15 else "平均ST"

                    race_info = {
                        "jcd": jcd, "name": v["name"], "rno": rno,
                        "time": rtimes.get(rno, "--:--"),
                        "pred_str": pred_str,
                        "attack_course": best_c,
                        "st_info": st_info,
                        "st_src": st_src,
                        "score": best["score"],
                        "stars": best["stars"],
                        "reasons": best["reasons"],
                        "atk_name": racers[best_c-1].get("name",""),
                        "is_finished": False,
                        "hit": False,
                        "sanrentan": "未確定",
                        "payout": 0,
                        "n_bets": n_bets,
                    }

                    res = get_official_result(jcd, ds, rno)
                    if res:
                        race_info["is_finished"] = True
                        race_info["sanrentan"] = res["sanrentan"]
                        finished_count += 1
                        invested += n_bets * 100

                        if res["ranks"] in buy_patterns:
                            race_info["hit"] = True
                            race_info["payout"] = res["payout"]
                            returned += res["payout"]

                    matches.append(race_info)

            # スコア降順ソート
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
        st.markdown(f"<h3 style='margin-bottom:4px;'>🎯 狙い目レース : 計 {len(matches)} 件（スコア順）</h3>", unsafe_allow_html=True)
        st.caption("抽出条件: ST差＋モーター＋勝率＋級別＋決まり手＋壁の弱さ＋今節動態＋F持ちの8項目をスコアリング。スコア5.0以上を抽出。")

        roi_color = "#2D8C3C" if roi >= 100 else "#E8212A" if roi > 0 else "#fff"

        dash_html = (
            f"<div style='display:flex; justify-content:space-around; background:rgba(0,0,0,0.3); padding:16px; border-radius:8px; margin-top:12px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.1);'>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>終了済</span><br><span style='font-size:22px;font-weight:bold;'>{fin} <span style='font-size:14px;'>件</span></span></div>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>投資 (各{'{'}点数{'}'}×100円)</span><br><span style='font-size:22px;font-weight:bold;'>{inv:,} <span style='font-size:14px;'>円</span></span></div>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>払戻合計</span><br><span style='font-size:22px;font-weight:bold;color:{roi_color};'>{ret:,} <span style='font-size:14px;'>円</span></span></div>"
            f"<div style='text-align:center;'><span style='font-size:12px;color:#aaa;'>回収率</span><br><span style='font-size:24px;font-weight:900;color:{roi_color};'>{roi:.1f} <span style='font-size:16px;'>%</span></span></div>"
            f"</div>"
        )
        st.markdown(dash_html, unsafe_allow_html=True)

        if matches:
            for m in matches:
                bg_color = "rgba(45, 140, 60, 0.2)" if m["hit"] else "rgba(255,255,255,0.03)"
                border_s = "border:1px solid #2D8C3C;" if m["hit"] else "border:1px solid rgba(255,255,255,0.1);"
                hit_badge = "<span style='background:#2D8C3C; color:#fff; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:bold;'>的中🎯</span>" if m["hit"] else ""

                # 信頼度の色
                sc = m["score"]
                if sc >= 14: sc_color = "#F5C518"
                elif sc >= 10: sc_color = "#E8212A"
                elif sc >= 7: sc_color = "#ff8c00"
                else: sc_color = "#aaa"

                reason_tags = " ".join(
                    f"<span style='background:rgba(255,255,255,0.08);padding:1px 6px;border-radius:3px;font-size:11px;color:#ccc;margin-right:4px;'>{r}</span>"
                    for r in m["reasons"]
                )

                card_html = (
                    f"<div style='background:{bg_color}; padding:12px 16px; border-radius:8px; {border_s} margin-bottom:10px;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;'>"
                    f"<div><span style='color:#E8212A;font-weight:bold;font-size:16px;'>{m['name']} {m['rno']}R</span>"
                    f"<span style='color:#ccc; font-size:13px; margin-left:8px;'>🕒 {m['time']}</span>"
                    f"<span style='margin-left:8px;font-size:13px;color:#aaa;'>{m['atk_name']}</span></div>"
                    f"<div style='display:flex;align-items:center;gap:8px;'>"
                    f"<span style='color:{sc_color};font-weight:900;font-size:18px;'>{m['stars']}</span>"
                    f"<span style='color:{sc_color};font-size:14px;font-weight:bold;'>{m['score']}pt</span>"
                    f"{hit_badge}</div></div>"
                    f"<div style='font-size:11px; color:#888; margin-bottom:4px;'>{m['st_src']}: {m['st_info']}</div>"
                    f"<div style='margin-bottom:6px;'>{reason_tags}</div>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; font-size:15px; padding-top:4px; border-top:1px dashed rgba(255,255,255,0.1);'>"
                    f"<div style='color:#F5C518;'><span style='font-size:12px; color:#aaa;'>{m['attack_course']}C強襲:</span> "
                    f"<span style='font-weight:900; font-size:17px; letter-spacing:1px;'>{m['pred_str']}</span></div>"
                    f"<div style='text-align:right;'><span style='font-size:12px; color:#aaa;'>3連単結果:</span> "
                    f"<span style='font-weight:bold;'>{m['sanrentan']}</span></div>"
                    f"</div></div>"
                )
                st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning("本日は条件に合致する狙い目レースが見つかりませんでした。")

        if st.button("✖ 検索結果を閉じる", key="close_search"):
            st.session_state["search_done"] = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

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

    # STEP3は簡易化（スリット検索を主眼にするため詳細解析表示は割愛・またはそのまま維持）
    # ※本スクリプトでは検索機能をメインとしています。

if __name__=="__main__":
    main()
