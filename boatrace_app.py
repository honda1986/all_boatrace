"""
🚤 ボートレース予想アプリ v7.1 (1-3展開 高精度ハンター)
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

UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "ja,en;q=0.9"}

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
        nr_s = gv("勝率")
        r["national_rate"] = float(nr_s) if re.match(r'^\d+\.\d+$', nr_s) else 5.0

        motor_2ren = 33.0
        for tr in rows:
            cells = tr.find_all(["td","th"])
            texts2 = [c.get_text(strip=True) for c in cells]
            if "モーター" in " ".join(texts2) and len(texts2) >= 7:
                if "2連率" in " ".join(texts2[:-6]).strip():
                    val = texts2[-6:][i]
                    if re.match(r'^[\d.]+$', val):
                        motor_2ren = float(val)
                        break
        r["motor_2ren"] = motor_2ren
        
        st_s = gv("ST")
        r["avg_st"] = float(st_s) if re.match(r'^0\.\d+$', st_s) else 0.15

        session_st = 0.15
        for tr in rows:
            cells = tr.find_all(["td","th"])
            texts2 = [c.get_text(strip=True) for c in cells]
            if "今節成績" in " ".join(texts2) and len(texts2) >= 7:
                label2 = " ".join(texts2[:-6]).strip()
                val = texts2[-6:][i]
                if "ST" in label2 and re.match(r'^[\d.]+$', val):
                    session_st = float(val)

        r["session_st"] = session_st
        racers.append(r)
    return racers

# ━━━━━━━━━━━ メイン解析ロジック ━━━━━━━━━━━

def get_eff_st(r):
    """節間ST優先、未走なら平均ST"""
    s = r.get("session_st", 0)
    return s if (s > 0 and s != 0.15) else r.get("avg_st", 0.15)

def evaluate_13_pattern(racers, jcd):
    """1-3展開（1着1号艇・2着3号艇）に特化した高精度スコアリング"""
    r1, r2, r3, r4 = racers[0], racers[1], racers[2], racers[3]
    score = 0.0
    reasons = []

    st1 = get_eff_st(r1)
    st2 = get_eff_st(r2)
    st3 = get_eff_st(r3)
    st4 = get_eff_st(r4)

    nr1 = r1.get("national_rate", 5.0)
    nr2 = r2.get("national_rate", 5.0)
    nr3 = r3.get("national_rate", 5.0)
    nr4 = r4.get("national_rate", 5.0)

    # ━━━ 1. 必須条件（強烈な足切り） ━━━
    
    # ① 1号艇の信頼度 (勝率6.0以上 または A級必須、かつST遅れなし)
    if nr1 < 6.0 and r1.get("class", "B1") not in ["A1", "A2"]: return None
    if st1 > 0.16: return None

    # ② 2号艇が「壁」にならないこと（最大のノイズである1-2決着の排除）
    # 2号艇が3号艇より勝率が高く、かつSTも同等以上の場合は1-2濃厚として除外
    if nr2 >= nr3 and st2 <= st3 + 0.01: return None
    # 2号艇がA1級の場合は、2着に残る確率が高すぎるため除外
    if r2.get("class", "B1") == "A1": return None

    # ③ 3号艇の地力 (3着以内に入る自力が必須)
    if nr3 < 5.0: return None

    # ④ 4号艇（カド）の強襲リスク排除
    # 4Cが3Cより極端にSTが早い、かつA級以上の場合は3Cが潰されるため除外
    if st4 < st3 - 0.03 and r4.get("class", "B1") in ["A1", "A2"]: return None

    # ━━━ 2. スコアリング ━━━
    
    # [1号艇の逃げ力]
    if nr1 >= 7.0: score += 4; reasons.append(f"1C勝率{nr1:.1f}")
    elif nr1 >= 6.5: score += 2; reasons.append(f"1C勝率{nr1:.1f}")
    if r1.get("motor_2ren", 33) >= 40: score += 2; reasons.append("1C機力◎")

    # [2号艇の弱さ vs 3号艇の強さ] (★最重要ポイント★)
    # STの比較（3号艇が2号艇を叩けるか）
    if st3 < st2 - 0.03:
        score += 5; reasons.append(f"3C先行ｽﾘｯﾄ({st3:.2f}<{st2:.2f})")
    elif st3 < st2:
        score += 3; reasons.append(f"3C-ST優位")
    else:
        score -= 3 # 3CのSTが遅いと2Cを越えられない

    # 勝率の比較（3号艇が2号艇を圧倒しているか）
    if nr3 - nr2 >= 1.5:
        score += 5; reasons.append(f"3C勝率圧倒({nr3:.1f}>{nr2:.1f})")
    elif nr3 - nr2 >= 0.5:
        score += 3; reasons.append("3C勝率優位")

    # 3号艇自体のポテンシャル
    if r3.get("class", "B1") == "A1": score += 3; reasons.append("3C=A1級")
    if r3.get("motor_2ren", 33) >= 40: score += 2; reasons.append("3C機力◎")

    # [4号艇の壁化]
    if st4 >= st3 + 0.02:
        score += 2; reasons.append("4C遅れ・3C壁化")

    # [5,6号艇の脅威チェック]
    out_threat = max(racers[4].get("national_rate", 5.0), racers[5].get("national_rate", 5.0))
    if out_threat >= 6.5:
        score -= 3; reasons.append("外枠に実力者あり")

    # 場別イン補正
    in_adj = IN_ADJ.get(jcd, 0)
    if in_adj >= 1.5: score += 1
    elif in_adj <= -1.5: score -= 1

    # ━━━ 3. 閾値（厳選） ━━━
    if score < 13: return None # ノイズを減らすため基準高め

    stars = "★★★" if score >= 19 else "★★☆" if score >= 16 else "★☆☆"

    return {
        "score": round(score, 1),
        "stars": stars,
        "reasons": reasons,
        "st_info": f"1C({st1:.2f}) 2C({st2:.2f}) 3C({st3:.2f}) 4C({st4:.2f})",
        "pw_info": f"1C({nr1:.1f}) 2C({nr2:.1f}) 3C({nr3:.1f}) 4C({nr4:.1f})",
    }

# ━━━━━━━━━━━ UI ━━━━━━━━━━━
def main():
    st.set_page_config(page_title="🚤 1-3展開 高精度ハンター",page_icon="🚤",layout="wide",initial_sidebar_state="collapsed")
    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap');
    .stApp{background:linear-gradient(135deg,#0a0a1a,#0d1b2a 40%,#1b2838);font-family:'Noto Sans JP',sans-serif}
    .hdr{background:linear-gradient(90deg,#E8212A,#B71C1C);padding:16px 24px;border-radius:12px;display:flex;align-items:center;gap:14px;box-shadow:0 4px 20px rgba(232,33,42,0.35);margin-bottom:16px}
    .hdr h1{color:#FFF!important;font-size:22px!important;font-weight:900!important;letter-spacing:3px;margin:0!important;padding:0!important}
    .hdr .sub{color:#ffcdd2;font-size:11px;letter-spacing:1px}
    .card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:16px;margin-bottom:12px}
    .sl{font-size:12px;font-weight:700;color:#E8212A;letter-spacing:2px;margin-bottom:8px}
    </style>""",unsafe_allow_html=True)
    
    st.markdown('<div class="hdr"><span style="font-size:32px">🚤</span><div><h1>BOAT RACE AI</h1><div class="sub">v7.1 ─ 1-3展開 高精度ハンター (2号艇沈み検知)</div></div></div>',unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="sl">STEP 1 ─ 開催日</div>',unsafe_allow_html=True)
    sel_date=st.date_input("日付",value=date.today(),label_visibility="collapsed")
    ds=sel_date.strftime("%Y-%m-%d")
    st.markdown('</div>',unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="sl">STEP 2 ─ 開催場</div>',unsafe_allow_html=True)
    with st.spinner("🔍 開催場を取得中..."): venues=get_active_venues(ds)
    if not venues: st.warning("⚠️ 開催情報なし"); st.markdown('</div>',unsafe_allow_html=True); return

    BUY_PATTERNS = [[1,3,2], [1,3,4], [1,3,5], [1,3,6]]
    N_BETS = len(BUY_PATTERNS)
    PRED_STR = f"1-3-全 ({N_BETS}点)"

    if st.button(f"🎯 1-3展開を検索（厳格フィルター適用）", type="primary", use_container_width=True):
        with st.spinner("全国のレースから高精度の1-3展開を抽出中..."):
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

                    ev = evaluate_13_pattern(racers, jcd)
                    if not ev: continue

                    race_info = {
                        "jcd": jcd, "name": v["name"], "rno": rno,
                        "time": rtimes.get(rno, "--:--"),
                        "pred_str": PRED_STR,
                        "st_info": ev["st_info"],
                        "pw_info": ev["pw_info"],
                        "score": ev["score"],
                        "stars": ev["stars"],
                        "reasons": ev["reasons"],
                        "r1_name": racers[0].get("name", ""),
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
                        invested += N_BETS * 100

                        if res["ranks"] in BUY_PATTERNS:
                            race_info["hit"] = True
                            race_info["payout"] = res["payout"]
                            race_info["result_str"] = f"🎯 {res['sanrentan']}"
                            returned += res["payout"]

                    matches.append(race_info)

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
        st.markdown(f"<h3 style='margin-bottom:4px;'>🎯 1-3展開(高精度版): 計 {len(matches)} 件</h3>", unsafe_allow_html=True)
        
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
                sc_color = "#F5C518" if sc >= 19 else "#E8212A" if sc >= 16 else "#ff8c00"

                reason_tags = " ".join(
                    f"<span style='background:rgba(255,255,255,0.08);padding:1px 6px;border-radius:3px;font-size:11px;color:#ccc;margin-right:4px;'>{r}</span>"
                    for r in m["reasons"]
                )

                card_html = (
                    f"<div style='background:{bg_color}; padding:12px 16px; border-radius:8px; {border_s} margin-bottom:10px;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;'>"
                    f"<div><span style='color:#E8212A;font-weight:bold;font-size:16px;'>{m['name']} {m['rno']}R</span>"
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
                    f"<span style='font-weight:900; font-size:17px; letter-spacing:1px;'>{m['pred_str']}</span></div>"
                    f"<div style='text-align:right;'><span style='font-size:12px; color:#aaa;'>結果:</span> "
                    f"<span style='font-weight:bold;'>{m['result_str']}</span></div>"
                    f"</div></div>"
                )
                st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning("本日は高精度の1-3展開条件に合致するレースが見つかりませんでした。")

        if st.button("✖ 検索結果を閉じる", key="close_search"):
            st.session_state["search_done"] = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.success(f"📍 {len(venues)}場開催中")

if __name__=="__main__":
    main()
