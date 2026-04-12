"""
🚤 ボートレース予想アプリ v3.1
━━━━━━━━━━━━━━━━━━━━━━━━
データソース:
  - boatrace.jp: 開催場一覧・出走表・直前情報・コース別成績(⑬)
  - boatrace-db.net: 節間成績(⑨)・レース結果・3連単払戻金

起動: pip install streamlit requests beautifulsoup4 lxml pandas
      streamlit run boatrace_app.py
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
    "01": {"name": "桐生",   "in_adj": -1.5, "rough": False},
    "02": {"name": "戸田",   "in_adj": -3.0, "rough": True},
    "03": {"name": "江戸川", "in_adj": -3.0, "rough": True},
    "04": {"name": "平和島", "in_adj": -3.0, "rough": True},
    "05": {"name": "多摩川", "in_adj": -1.5, "rough": False},
    "06": {"name": "浜名湖", "in_adj": 0,    "rough": False},
    "07": {"name": "蒲郡",   "in_adj": 0,    "rough": False},
    "08": {"name": "常滑",   "in_adj": 0,    "rough": False},
    "09": {"name": "津",     "in_adj": 0,    "rough": False},
    "10": {"name": "三国",   "in_adj": 0,    "rough": False},
    "11": {"name": "びわこ", "in_adj": -1.5, "rough": False},
    "12": {"name": "住之江", "in_adj": 1.5,  "rough": False},
    "13": {"name": "尼崎",   "in_adj": 0,    "rough": False},
    "14": {"name": "鳴門",   "in_adj": 0,    "rough": False},
    "15": {"name": "丸亀",   "in_adj": 1.5,  "rough": False},
    "16": {"name": "児島",   "in_adj": 0,    "rough": False},
    "17": {"name": "宮島",   "in_adj": 0,    "rough": False},
    "18": {"name": "徳山",   "in_adj": 3.0,  "rough": False},
    "19": {"name": "下関",   "in_adj": 1.5,  "rough": False},
    "20": {"name": "若松",   "in_adj": 0,    "rough": False},
    "21": {"name": "芦屋",   "in_adj": 3.0,  "rough": False},
    "22": {"name": "福岡",   "in_adj": 0,    "rough": False},
    "23": {"name": "唐津",   "in_adj": 0,    "rough": False},
    "24": {"name": "大村",   "in_adj": 3.0,  "rough": False},
}

COURSE_CSS = {
    1: "background:#FFF;color:#000;border:1.5px solid #999;",
    2: "background:#000;color:#FFF;",
    3: "background:#E8212A;color:#FFF;",
    4: "background:#1B6DB5;color:#FFF;",
    5: "background:#F5C518;color:#000;",
    6: "background:#2D8C3C;color:#FFF;",
}

NATIONAL_REN3 = {1: 81, 2: 59, 3: 54, 4: 50, 5: 37, 6: 22}

UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "ja,en;q=0.9"}

# ━━━━━━━━━━━ 共通 ━━━━━━━━━━━

def _make_session():
    """リトライ付きセッション"""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers.update(HEADERS)
    return s

@st.cache_resource
def get_session():
    return _make_session()

@st.cache_data(ttl=180)
def fetch(url):
    s = get_session()
    r = s.get(url, timeout=30)
    r.encoding = "utf-8"
    return r.text

# ━━━━━━━━━━━ boatrace.jp ━━━━━━━━━━━

def get_active_venues(date_str):
    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={hd}"
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
        seen, out = set(), []
        for a in soup.find_all("a", href=True):
            if "raceindex" in a["href"] and f"hd={hd}" in a["href"]:
                m = re.search(r"jcd=(\d{2})", a["href"])
                if m and m.group(1) in VENUES and m.group(1) not in seen:
                    seen.add(m.group(1))
                    j = m.group(1)
                    out.append({"jcd": j, "name": VENUES[j]["name"], "in_adj": VENUES[j]["in_adj"]})
        return out
    except Exception as e:
        st.error(f"開催場取得失敗: {e}")
        return []


def get_race_times(jcd, date_str):
    hd = date_str.replace("-", "")
    times = {}
    try:
        text = BeautifulSoup(fetch(
            f"https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={jcd}&hd={hd}"
        ), "html.parser").get_text()
        valid = []
        for t in re.findall(r'(\d{1,2}:\d{2})', text):
            if 8 <= int(t.split(":")[0]) <= 21 and t not in valid:
                valid.append(t)
        for i, t in enumerate(valid[:12]):
            times[i + 1] = t
    except Exception:
        pass
    return times


def get_race_card(jcd, date_str, rno):
    hd = date_str.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd}&hd={hd}"
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
        EXCLUDE = {"東京","大阪","福岡","愛知","埼玉","群馬","静岡","長崎","広島",
                    "岡山","山口","三重","徳島","香川","佐賀","熊本","千葉","茨城",
                    "栃木","長野","新潟","富山","石川","福井","滋賀","京都","兵庫",
                    "奈良","鳥取","島根","高知","愛媛","宮崎","鹿児島","沖縄",
                    "北海道","青森","岩手","宮城","秋田","山形","福島","山梨",
                    "岐阜","大分","和歌山","神奈川"}
        racers = []
        racer_tbs = [tb for tb in soup.find_all("tbody")
                     if re.search(r'\d{4}', tb.get_text()) and re.search(r'[AB][12]', tb.get_text())]
        for i, tb in enumerate(racer_tbs[:6], 1):
            txt = tb.get_text(separator="|", strip=True)
            cells = [c.strip() for c in txt.split("|") if c.strip()]
            reg = next((c for c in cells if re.match(r'^\d{4}$', c)), "----")
            name = next((c.replace(" ","").replace("　","") for c in cells
                         if 2<=len(c.replace(" ","").replace("　",""))<=4
                         and re.match(r'^[一-龥ぁ-んァ-ヴー\s　]+$', c)
                         and c.replace(" ","").replace("　","") not in EXCLUDE), f"選手{i}")
            cls = next((c for c in cells if c in ("A1","A2","B1","B2")), "B1")
            all_n = re.findall(r'\d+\.?\d*', txt)
            age = next((int(float(n)) for n in all_n if 18<=float(n)<=70 and float(n)==int(float(n))), 35)
            rates = [float(n) for n in all_n if re.match(r'^\d\.\d{2}$', n) and 2<=float(n)<=10]
            nr = rates[0] if rates else 5.0
            lr = rates[1] if len(rates)>=2 else nr
            motor = 33.0
            for n in all_n:
                if re.match(r'^\d{2}\.\d$', n):
                    v = float(n)
                    if 15<=v<=75 and v!=nr and v!=lr:
                        motor = v; break
            fm = re.search(r'F(\d)', txt)
            fc = int(fm.group(1)) if fm else 0
            st_v = next((float(n) for n in all_n if re.match(r'^0\.\d{2}$', n) and 0.01<=float(n)<=0.40), 0.15)
            racers.append({"course":i,"number":reg,"name":name,"class":cls,"age":age,
                           "national_rate":nr,"local_rate":lr,"motor_2ren":motor,"f_count":fc,"avg_st":st_v})
        while len(racers) < 6:
            c = len(racers)+1
            racers.append({"course":c,"number":"----","name":f"選手{c}","class":"B1",
                           "age":30,"national_rate":5.0,"local_rate":5.0,"motor_2ren":33.0,"f_count":0,"avg_st":0.15})
        return racers
    except Exception as e:
        st.error(f"出走表取得失敗: {e}")
        return []


def get_before_info(jcd, date_str, rno):
    hd = date_str.replace("-", "")
    res = {"weather":{"wind_dir":"","wind_speed":0,"wave":0},"exhibition_times":{}}
    try:
        text = BeautifulSoup(fetch(
            f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={hd}"
        ), "html.parser").get_text(separator=" ", strip=True)
        for wd in ["追い風","向かい風","右横風","左横風"]:
            if wd in text: res["weather"]["wind_dir"]=wd; break
        for m in re.finditer(r'(?<!\d)(\d{1,2})m(?![0-9])', text):
            ws=int(m.group(1))
            if 0<ws<=15: res["weather"]["wind_speed"]=ws; break
        wm=re.search(r'(\d{1,2})\s*cm', text)
        if wm: res["weather"]["wave"]=int(wm.group(1))
        for i,t in enumerate(re.findall(r'\b(6\.\d{2}|7\.\d{2})\b', text)[:6]):
            res["exhibition_times"][i+1]=float(t)
    except Exception: pass
    return res

# ━━━━━━━━━━━ boatrace.jp コース別成績(⑬) ━━━━━━━━━━━

@st.cache_data(ttl=600)
def get_course_stats_bp(reg_number):
    """公式コース別成績ページから3連対率を取得"""
    if not reg_number or reg_number=="----": return {}
    url = f"https://www.boatrace.jp/owpc/pc/data/racersearch/course?toban={reg_number}"
    result = {}
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
        for tbl in soup.find_all("table"):
            txt = tbl.get_text(separator="|", strip=True)
            if "3連対率" not in txt: continue
            for row in tbl.find_all("tr"):
                cells = [c.get_text(strip=True) for c in row.find_all(["td","th"])]
                if len(cells)<2: continue
                m = re.search(r'(\d)', cells[0])
                if not m: continue
                cn = int(m.group(1))
                if not 1<=cn<=6: continue
                vm = re.search(r'([\d.]+)', cells[1].replace("%",""))
                if vm:
                    result[cn] = float(vm.group(1))
    except Exception: pass
    return result

# ━━━━━━━━━━━ boatrace-db.net ━━━━━━━━━━━

@st.cache_data(ttl=180)
def get_db_detail(jcd, date_str, rno):
    """
    boatrace-db.net レース詳細ページから:
    1. 各選手の節間成績（着順リスト）
    2. レース結果
    3. 3連単払戻金
    """
    hd = date_str.replace("-","")
    url = f"https://boatrace-db.net/race/detail/date/{hd}/pid/{jcd}/rno/{rno}/"
    out = {"session":{}, "trifecta":"", "trifecta_payout":0, "result_order":[], "raw":"", "debug":""}

    try:
        html = fetch(url)
        soup = BeautifulSoup(html, "html.parser")
        full = soup.get_text(separator="\n", strip=True)
        out["raw"] = full[:3000]  # デバッグ用

        # ── 選手セクション解析 ──
        # 各選手テーブルから登録番号を検出し、着順行を抽出
        tables = soup.find_all("table")
        boat_idx = 0

        for tbl in tables:
            tbl_text = tbl.get_text(separator="|", strip=True)

            # 選手テーブルの判定: 4桁登録番号 + 級別
            reg_m = re.search(r'\b(\d{4})\b', tbl_text)
            cls_m = re.search(r'\b(A1|A2|B1|B2)\b', tbl_text)
            if not reg_m or not cls_m:
                continue

            # 「初日」「2日目」等のキーワードがあれば節間データテーブル
            if not re.search(r'(初日|[2-6２-６]日目|最終日)', tbl_text):
                continue

            boat_idx += 1
            if boat_idx > 6:
                break

            # 全行のセルデータを収集
            rows_data = []
            for tr in tbl.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td","th"])]
                rows_data.append(cells)

            # 結果行を特定: 1-6の数字が多い行、かつR表記や日付がない行
            best_results = []
            for cells in rows_data:
                nums = []
                skip = False
                for c in cells:
                    c = c.strip()
                    if c.isdigit() and 1<=int(c)<=6:
                        nums.append(int(c))
                    elif re.match(r'^\d+R$', c) or c in ("初日","2日目","3日目","4日目","5日目","6日目","最終日"):
                        skip = True
                        break
                    elif c in ("F","転","落","エ","欠","不","妨","失"):
                        nums.append(0)  # 特殊結果は0扱い
                if not skip and len(nums) >= 1 and len(nums) > len(best_results):
                    best_results = nums

            if best_results:
                out["session"][boat_idx] = {
                    "number": reg_m.group(1),
                    "class": cls_m.group(1),
                    "results": [r for r in best_results if r > 0],  # 0(F等)を除外
                }

        # ── 3連単払戻金 ──
        # パターン1: テーブル内
        for tbl in tables:
            txt = tbl.get_text(separator="|", strip=True)
            if "3連単" in txt:
                # 3連単|1-2-3|12,345円  or  3連単|1=2=3|12345円
                m = re.search(r'3連単[|]\s*(\d[\s]*[-=＝]\s*\d[\s]*[-=＝]\s*\d)[|]\s*([\d,]+)\s*円', txt)
                if m:
                    out["trifecta"] = re.sub(r'[\s＝=]', '-', m.group(1))
                    out["trifecta_payout"] = int(m.group(2).replace(",",""))
                    break

        # パターン2: テキスト全体から
        if not out["trifecta"]:
            m = re.search(r'3連単[\s|]*(\d\s*[-=＝ー－]\s*\d\s*[-=＝ー－]\s*\d)\s*[\s|]*([\d,]+)\s*円', full)
            if m:
                out["trifecta"] = re.sub(r'[\s＝=ー－]', '-', m.group(1))
                out["trifecta_payout"] = int(m.group(2).replace(",",""))

        # ── 着順（結果） ──
        # 1着-2着-3着 の組み合わせから取得
        if out["trifecta"]:
            parts = out["trifecta"].split("-")
            if len(parts)==3:
                out["result_order"] = [int(p) for p in parts if p.isdigit()]

    except Exception as e:
        out["debug"] = str(e)

    return out


# ━━━━━━━━━━━ スコアリング ━━━━━━━━━━━

def calc_trend_score(results):
    """⑨節間順位動態"""
    s, notes = 0.0, []
    if not results or len(results)<2:
        return 0, ["⑨データ不足"]
    r = results  # 古い順
    recent = list(reversed(r))  # 最新が先頭

    if len(recent)>=2 and recent[0]==1 and recent[1]==1:
        s+=2.0; notes.append("⑨直近2走連続1着+2.0")
    elif len(recent)>=2 and recent[0]<=2 and recent[1]<=2:
        s+=1.0; notes.append("⑨直近2走2着内+1.0")
    if len(recent)>=3 and recent[2]>recent[1]>recent[0]:
        s+=1.5; notes.append("⑨3走連続改善+1.5")
    if len(recent)>=3 and all(x>=4 for x in recent[:3]):
        s-=2.0; notes.append("⑨3走連続着外-2.0")
    if recent[0]==6:
        s-=1.5; notes.append("⑨直近6着-1.5")
    if len(recent)>=4:
        r2 = sum(1 for x in recent if x<=2)/len(recent)*100
        if r2>=60: s+=1.0; notes.append(f"⑨節間2連率{r2:.0f}%+1.0")
        elif r2<=15: s-=1.0; notes.append(f"⑨節間2連率{r2:.0f}%-1.0")
    return round(s,1), notes


def calc_course13(course, ren3_map):
    """⑬コース別成績(3連対率ベース)"""
    s, notes = 0.0, []
    if course not in ren3_map:
        return 0, ["⑬データなし"]
    val = ren3_map[course]
    avg = NATIONAL_REN3.get(course, 50)
    diff = val - avg
    if diff>=15:   s+=3.0; notes.append(f"⑬コース巧者(3連率{val:.1f}%,+{diff:.0f}%)")
    elif diff>=8:  s+=1.5; notes.append(f"⑬コース得意(3連率{val:.1f}%)")
    elif diff<=-15: s-=2.5; notes.append(f"⑬コース苦手(3連率{val:.1f}%)")
    elif diff<=-8: s-=1.0; notes.append(f"⑬やや苦手(3連率{val:.1f}%)")
    if course==1 and val>=90:
        s+=1.0; notes.append("⑬イン巧者+1.0")
    if course>=4 and avg>0 and val>=avg*1.5:
        s+=1.5; notes.append("⑬まくり屋+1.5")
    all_v = [ren3_map[c] for c in range(1,7) if c in ren3_map]
    if len(all_v)>=4 and sum(all_v)/len(all_v)>=65:
        s+=1.0; notes.append("⑬総合安定+1.0")
    return round(s,1), notes


def calc_scores(racers, jcd, weather, ex_times, db_data, course_stats_map,
                is_day1=False, is_final=False):
    venue = VENUES[jcd]
    ex_sorted = sorted(ex_times.items(), key=lambda x:x[1]) if ex_times else []
    ex_rank = {c:r for r,(c,_) in enumerate(ex_sorted,1)}
    scored = []

    for r in racers:
        c = r["course"]; sc = {}; notes = []

        # ① コース基礎
        s1 = {1:7,2:5,3:4,4:3.5,5:3,6:1.5}.get(c,3)
        if is_final and c==1: s1=12; notes.append("優勝戦1C")
        sc["コース基礎"]=s1

        # ② 場別イン
        sc["場別イン"]=venue["in_adj"] if c==1 else 0

        # ③ 風速波高
        s3=0; ws=weather.get("wind_speed",0); wd=weather.get("wind_dir",""); wv=weather.get("wave",0)
        if "追い風" in wd and ws>=5:
            if c==1: s3-=2.5
            if c==2: s3+=1.5
        elif "追い風" in wd and 3<=ws<=4:
            if c==1: s3-=1.0; 
            if c==3: s3+=0.5
        elif "向かい風" in wd and ws>=5:
            if c==1: s3-=2.5
            if c==4: s3+=1.5
        if wv>=8 and c==1: s3-=3.0; notes.append("高波警戒")
        sc["風速波高"]=s3

        # ④ モーター
        mr=r.get("motor_2ren",33)
        s4=3.0 if mr>50 else 1.5 if mr>=40 else 0.5 if mr>=30 else -2.0 if mr<25 else 0
        if is_day1: s4*=0.5; notes.append("初日Mo0.5倍")
        sc["モーター"]=s4

        # ⑤ 展示タイム
        s5=0
        if c in ex_rank:
            rk=ex_rank[c]
            if rk==1 and len(ex_sorted)>1:
                d=ex_sorted[1][1]-ex_sorted[0][1]
                s5=2.0 if d>=0.07 else 1.0 if d>=0.04 else 0
            elif rk==2 and len(ex_sorted)>2:
                d=ex_sorted[2][1]-ex_times[c]
                s5=1.0 if d>=0.04 else 0
            if rk==6: s5=-3.0 if c==1 else -2.0
            if rk==6 and c==1: notes.append("⚠イン崩壊フラグ")
        sc["展示タイム"]=s5

        # ⑥ 平均ST
        st=r.get("avg_st",0.15)
        sc["平均ST"]=2.0 if st<=0.10 else 1.0 if st<=0.13 else -2.0 if st>=0.20 else -1.0 if st>=0.17 else 0

        # ⑦ Fペナ
        fc=r.get("f_count",0)
        sc["Fペナ"]=-3.0 if fc>=2 else (-2.0 if c>=4 else -1.0) if fc==1 else 0

        # ⑧ 選手力
        nr=r.get("national_rate",5.0)
        s8=3.5 if nr>=8 else 3.0 if nr>=7.5 else 2.0 if nr>=7 else 1.0 if nr>=6 else 0 if nr>=5 else -1.0 if nr>=4 else -2.0
        if venue["rough"] and r.get("local_rate",5.0)>=nr+0.5:
            s8+=1.0; notes.append("難水面適性+1")
        sc["選手力"]=s8

        # ⑨ 節間動態（boatrace-db.net）
        s9=0
        db_racer = db_data.get("session",{}).get(c,{})
        if db_racer and db_racer.get("results"):
            s9, tn = calc_trend_score(db_racer["results"])
            notes.extend(tn)
        else:
            notes.append("⑨節間データなし")
        sc["節間動態"]=s9

        # ⑩ 進入変動
        sc["進入変動"]=0

        # ⑪ クラス
        sc["クラス"]={"A1":2.5,"A2":1.0,"B1":0,"B2":-2.0}.get(r.get("class","B1"),0)

        # ⑫ 年齢
        age=r.get("age",30); cr=r.get("class","B1")
        s12=1.0 if 25<=age<=35 else 0.5 if 36<=age<=44 else 0 if 45<=age<=50 else -0.5 if age>=51 else -0.5 if age<=24 else 0
        if cr=="A1" and age>=50 and s12<0: s12=0; notes.append("A1ベテラン補正")
        sc["年齢"]=s12

        # ⑬ コース別成績（boatrace.jp個人ページ）
        s13=0
        ren3_map = course_stats_map.get(r.get("number",""),{})
        if ren3_map:
            s13, cn = calc_course13(c, ren3_map)
            notes.extend(cn)
        else:
            notes.append("⑬データなし")
        sc["コース別"]=s13

        # ⑭ 当地
        lr=r.get("local_rate",5.0)
        s14=2.0 if lr>=nr+1.0 else 1.0 if lr>=nr+0.5 else -1.5 if lr<=nr-1.0 else -0.5 if lr<=nr-0.5 else 0
        if c==1 and lr>=6.5: s14+=1.5; notes.append("当地6.5↑1C:+1.5")
        sc["当地"]=s14

        total=round(sum(sc.values()),1)
        scored.append({**r,"scores":sc,"total":total,"notes":notes})
    return sorted(scored, key=lambda x:x["total"], reverse=True)


# ━━━━━━━━━━━ 買い目生成 ━━━━━━━━━━━

def generate_scenario(scored, weather, jcd):
    by_c={r["course"]:r for r in scored}
    top=scored[0]; sec=scored[1] if len(scored)>1 else None
    gap=round(top["total"]-sec["total"],1) if sec else 99

    if top["course"]==1:   pat="逃げ"; txt=f"1C {by_c.get(1,{}).get('name','')} イン逃げ本線。"
    elif top["course"]==2: pat="差し"; txt=f"2C {top.get('name','')} の差し展開。"
    elif top["course"]==3: pat="まくり差し"; txt=f"3C {top.get('name','')} のまくり差し。"
    elif top["course"] in (4,5,6): pat="まくり"; txt=f"{top['course']}C {top.get('name','')} の外まくり。荒れ模様。"
    else: pat="混戦"; txt="混戦模様。"

    ws=weather.get("wind_speed",0); wd=weather.get("wind_dir","")
    if ws>=5: txt+=f" {wd}{ws}m影響大。"
    if weather.get("wave",0)>=8: txt+=" 高波注意。"

    if gap>=4:   fr,conf=0.60,"高"
    elif gap>=2: fr,conf=0.45,"中"
    elif gap>=1: fr,conf=0.33,"低"
    else:        fr,conf=0.25,"極低"

    # 2着候補率（展開パターン + スコア）
    pat2={}
    if pat=="逃げ":       pat2={2:0.34,3:0.27}
    elif pat=="差し":     pat2={1:0.60,3:0.15}
    elif pat=="まくり差し":pat2={1:0.55,2:0.15}
    elif pat=="まくり":
        o=min(top["course"]+1,6)
        pat2={1:0.30,o:0.40}

    s2={}
    for r in scored:
        cc=r["course"]
        if cc==top["course"]: continue
        base=pat2.get(cc,0.05)
        rank_i=scored.index(r)
        mult=1.3 if rank_i<=1 else 1.1 if rank_i<=2 else 0.6 if rank_i>=4 else 0.9
        s2[cc]=round(base*mult,4)
    sr_s=sum(s2.values())
    if sr_s>0: s2={k:round(v/sr_s,4) for k,v in s2.items()}

    # 推奨
    if gap<1:
        rtype="見送り"; reason=f"スコア差{gap}pt→完全混戦"; fms=[]; btype=""
    elif gap<2:
        rtype="注意"; reason=f"スコア差{gap}pt→混戦。穴目検討"
        fms=[f"{top['course']}-{scored[1]['course']}-全",f"{scored[1]['course']}-{top['course']}-全"]
        btype="3連単(穴型)"
    else:
        rtype="買い"; reason=f"スコア差{gap}pt→{top.get('name','')}({top['course']}C)有力"
        t2=sorted(s2.items(),key=lambda x:x[1],reverse=True)[:2]
        fms=[f"{top['course']}-{'/'.join(str(x[0]) for x in t2)}-全"]
        btype="3連単(基本型)" if gap>=4 else "3連単(標準型)"

    # 全買い目
    bets=[]
    if rtype!="見送り":
        tc=top["course"]
        firsts=[(tc,fr)]
        if rtype=="注意": firsts.append((scored[1]["course"],1.0-fr))
        for fc,f_r in firsts:
            s2c=sorted([(r["course"],s2.get(r["course"],0.05)) for r in scored if r["course"]!=fc],
                       key=lambda x:x[1],reverse=True)[:3]
            for sc,sr in s2c:
                rem=[r for r in scored if r["course"] not in (fc,sc)]
                for tr in rem[:3]:
                    tc2=tr["course"]
                    tots=[max(r["total"]+26.5,0.5) for r in rem]
                    ts=sum(tots)
                    t_r=next((tots[i]/ts for i,r2 in enumerate(rem) if r2["course"]==tc2),0.25) if ts>0 else 0.25
                    hit=round(f_r*sr*t_r,5)
                    if hit>0.001:
                        lbl="◎本命" if hit>=0.08 else "○対抗" if hit>=0.04 else "▲連下" if hit>=0.02 else "△押さえ"
                        bets.append({"bet":f"{fc}-{sc}-{tc2}","hit_rate":hit,
                                     "req_odds":round(1/hit,1) if hit>0 else 999,"note":lbl})
    seen=set()
    ubets=[]
    for b in sorted(bets,key=lambda x:x["hit_rate"],reverse=True):
        if b["bet"] not in seen: seen.add(b["bet"]); ubets.append(b)
    return {"scenario":txt,"pattern":pat,"rec_type":rtype,"rec_reason":reason,
            "formations":fms,"bet_type":btype,"bets":ubets[:12],"score_gap":gap,"confidence":conf}


# ━━━━━━━━━━━ 表示ヘルパー ━━━━━━━━━━━

def badge(c):
    css=COURSE_CSS.get(c,"background:#888;color:#FFF;")
    return f'<span style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:5px;font-weight:900;font-size:15px;{css}">{c}</span>'

def bar(score):
    rng=62; pct=max(0,min(100,(score+26)/rng*100)); zp=26/rng*100
    clr="#E8212A" if score>=20 else "#F5C518" if score>=12 else "#1B6DB5" if score>=5 else "#888"
    left=zp if score>=0 else pct; w=abs(pct-zp)
    return (f'<div style="height:20px;background:#1a1a2e;border-radius:10px;position:relative;overflow:hidden">'
            f'<div style="height:16px;border-radius:8px;margin-top:2px;margin-left:{left}%;width:{w}%;'
            f'background:linear-gradient(90deg,{clr}CC,{clr})"></div>'
            f'<span style="position:absolute;right:8px;top:0;line-height:20px;font-size:12px;font-weight:800;'
            f'color:#FFF;text-shadow:0 1px 3px rgba(0,0,0,0.8)">{score:.1f}</span></div>')


# ━━━━━━━━━━━ メインUI ━━━━━━━━━━━

def main():
    st.set_page_config(page_title="🚤 ボートレース予想AI v3",page_icon="🚤",layout="wide",initial_sidebar_state="collapsed")
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
    st.markdown('<div class="hdr"><span style="font-size:32px">🚤</span><div><h1>BOAT RACE AI</h1><div class="sub">v3.1 ─ 14項目解析 + boatrace-db.net連携</div></div></div>',unsafe_allow_html=True)

    # 接続チェック（初回のみ）
    if "conn_checked" not in st.session_state:
        st.session_state["conn_checked"] = True
        st.session_state["db_ok"] = False
        st.session_state["bp_ok"] = False
        try:
            requests.head("https://boatrace-db.net/", headers=HEADERS, timeout=5)
            st.session_state["db_ok"] = True
        except Exception:
            pass
        try:
            requests.head("https://www.boatrace.jp/", headers=HEADERS, timeout=5)
            st.session_state["bp_ok"] = True
        except Exception:
            pass

    if not st.session_state.get("db_ok") or not st.session_state.get("bp_ok"):
        problems = []
        if not st.session_state.get("bp_ok"): problems.append("boatrace.jp")
        if not st.session_state.get("db_ok"): problems.append("boatrace-db.net")
        st.error(
            f"⚠️ {' / '.join(problems)} に接続できません。\n\n"
            "**Streamlit Cloudからは日本の競艇サイトにアクセスできない場合があります。**\n\n"
            "**ローカルで実行してください:**\n"
            "```\npip install streamlit requests beautifulsoup4 lxml pandas\n"
            "streamlit run boatrace_app.py\n```"
        )
        if not st.session_state.get("bp_ok"):
            return  # boatrace.jpに繋がらなければ続行不可

    # STEP 1
    st.markdown('<div class="card"><div class="sl">STEP 1 ─ 開催日</div>',unsafe_allow_html=True)
    sel_date=st.date_input("日付",value=date.today(),label_visibility="collapsed")
    ds=sel_date.strftime("%Y-%m-%d"); is_past=sel_date<date.today()
    st.markdown('</div>',unsafe_allow_html=True)

    # STEP 2
    st.markdown('<div class="card"><div class="sl">STEP 2 ─ 開催場</div>',unsafe_allow_html=True)
    with st.spinner("🔍 検索中..."): venues=get_active_venues(ds)
    if not venues:
        st.warning(f"⚠️ {sel_date.strftime('%Y年%m月%d日')} の開催なし"); st.markdown('</div>',unsafe_allow_html=True); return
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
    vi=VENUES[sv]

    # STEP 3
    st.markdown(f'<div class="card"><div class="sl">STEP 3 ─ {vi["name"]} レース選択</div>',unsafe_allow_html=True)
    rtimes=get_race_times(sv,ds)
    r1c=st.columns(6)
    for i in range(6):
        rno=i+1
        with r1c[i]:
            t=rtimes.get(rno,""); lbl=f"{rno}R\n{t}" if t else f"{rno}R"
            if st.button(lbl,key=f"r{rno}",use_container_width=True): st.session_state["race"]=rno; st.rerun()
    r2c=st.columns(6)
    for i in range(6):
        rno=i+7
        with r2c[i]:
            t=rtimes.get(rno,""); pre="🏆" if rno==12 else ""
            lbl=f"{pre}{rno}R\n{t}" if t else f"{pre}{rno}R"
            if st.button(lbl,key=f"r{rno}",use_container_width=True): st.session_state["race"]=rno; st.rerun()
    st.markdown('</div>',unsafe_allow_html=True)
    sr=st.session_state.get("race")
    if not sr: return

    # ━━━ 解析 ━━━
    st.divider(); st.subheader(f"🏁 {vi['name']} {sr}R 解析")

    with st.spinner("📊 出走表・直前情報を取得中..."):
        racers=get_race_card(sv,ds,sr)
        before=get_before_info(sv,ds,sr)
    if not racers: st.error("❌ 出走表取得失敗"); return

    # boatrace-db.net から節間成績・結果・払戻
    db_data={"session":{},"trifecta":"","trifecta_payout":0,"debug":""}
    if st.session_state.get("db_ok", False):
        with st.spinner("📈 boatrace-db.net からデータ取得中..."):
            try:
                db_data=get_db_detail(sv,ds,sr)
            except Exception as e:
                db_data["debug"]=str(e)
                st.caption(f"⚠️ boatrace-db.net取得失敗（⑨=0で継続）")
    else:
        st.caption("ℹ️ boatrace-db.netに未接続のため⑨節間成績・払戻は取得スキップ")

    # コース別成績(⑬)
    course_stats_map={}
    if st.session_state.get("bp_ok", False):
        prog=st.progress(0,text="📈 コース別成績取得中...")
        for i,r in enumerate(racers):
            reg=r.get("number","----")
            if reg!="----":
                try:
                    cs=get_course_stats_bp(reg)
                    if cs: course_stats_map[reg]=cs
                except Exception:
                    pass
            prog.progress((i+1)/6,text=f"📈 コース別成績取得中... {i+1}/6")
            time.sleep(0.3)
        prog.empty()

    # スコアリング
    scored=calc_scores(racers,sv,before.get("weather",{}),before.get("exhibition_times",{}),
                       db_data,course_stats_map,is_day1=False,is_final=(sr==12))
    analysis=generate_scenario(scored,before.get("weather",{}),sv)

    # 天候
    w=before.get("weather",{})
    wp=[]
    if w.get("wind_dir"): wp.append(w["wind_dir"])
    if w.get("wind_speed"): wp.append(f"{w['wind_speed']}m")
    if w.get("wave"): wp.append(f"波高{w['wave']}cm")
    if wp: st.info(f"🌊 気象: {' / '.join(wp)}")

    # ── 過去レース結果・3連単 ──
    if is_past and (db_data.get("trifecta") or db_data.get("result_order")):
        st.markdown("#### 📋 レース結果")
        if db_data.get("result_order"):
            for i,bn in enumerate(db_data["result_order"][:3],1):
                emoji={1:"🥇",2:"🥈",3:"🥉"}.get(i,"")
                st.write(f"{emoji} **{i}着** {badge(bn)}",unsafe_allow_html=True)
        if db_data.get("trifecta"):
            st.markdown(f"#### 💰 3連単: **{db_data['trifecta']}** → **¥{db_data['trifecta_payout']:,}**")
        st.divider()
    elif is_past:
        st.info("このレースの結果はまだ取得できません。")

    # ── スコア一覧 ──
    st.markdown("#### 📊 全艇スコア一覧")
    for idx,r in enumerate(scored):
        crown="👑 " if idx==0 else ""; bg="rgba(245,197,24,0.06)" if idx==0 else "transparent"; nc2="#F5C518" if idx==0 else "#ddd"
        st.markdown(f'<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:{bg};border-radius:8px;margin-bottom:4px">{badge(r["course"])}<div style="min-width:80px;font-weight:700;font-size:14px;color:{nc2}">{crown}{r.get("name","")}</div><div style="min-width:60px;font-size:11px;color:#888">{r.get("class","")}/{r.get("national_rate",0)}</div><div style="flex:1">{bar(r["total"])}</div></div>',unsafe_allow_html=True)

    with st.expander("📋 スコア内訳"):
        rows=[{"コース":f'{r["course"]}C',"選手":r.get("name",""),"合計":r["total"],**r["scores"]} for r in scored]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        for r in scored:
            if r.get("notes"): st.caption(f'**{r["course"]}C {r.get("name","")}**: {" / ".join(r["notes"])}')

    # ── 節間成績・コース別成績の詳細 ──
    with st.expander("📈 選手個別データ（⑨⑬算出元）"):
        for r in racers:
            c=r["course"]; reg=r.get("number","")
            st.markdown(f"**{c}C {r.get('name','')}** (#{reg})")

            # ⑨ 節間着順（boatrace-db.net）
            db_r=db_data.get("session",{}).get(c,{})
            if db_r and db_r.get("results"):
                st.caption(f"⑨ 節間着順: {' → '.join(str(x) for x in db_r['results'])}")
            else:
                st.caption("⑨ 節間データ: 取得できず")

            # ⑬ コース別3連対率（boatrace.jp）
            ren3=course_stats_map.get(reg,{})
            if ren3:
                cs_rows=[]
                for cn in range(1,7):
                    if cn in ren3:
                        avg=NATIONAL_REN3.get(cn,50); diff=ren3[cn]-avg
                        mk=" 👈" if cn==c else ""
                        cs_rows.append({"":mk,"コース":f"{cn}C","3連対率":f"{ren3[cn]:.1f}%","全国平均":f"{avg}%","差分":f"{diff:+.1f}%"})
                if cs_rows: st.dataframe(pd.DataFrame(cs_rows),use_container_width=True,hide_index=True)
            else:
                st.caption("⑬ コース別: 取得できず")
            st.markdown("---")

    # ── 展開シナリオ ──
    st.markdown("#### 🌊 展開シナリオ")
    st.write(analysis["scenario"])
    top3=scored[:3]
    st.write(" / ".join([f"**{'本命' if i==0 else '対抗' if i==1 else '3番手'}**: {r['course']}C {r.get('name','')} ({r.get('class','')},勝率{r.get('national_rate',0)}) スコア{r['total']}" for i,r in enumerate(top3)]))
    c1,c2=st.columns(2)
    with c1: st.metric("決まり手予測",analysis["pattern"])
    with c2: st.metric("信頼度",analysis["confidence"])

    # ── 推奨判定 ──
    st.markdown("#### 🎯 推奨判定")
    rt=analysis["rec_type"]
    if rt=="見送り": st.warning(f"⚠️ **{rt}**\n\n{analysis['rec_reason']}")
    elif rt=="注意": st.info(f"⚡ **{rt}**\n\n{analysis['rec_reason']}")
    else: st.success(f"🎯 **{rt}**\n\n{analysis['rec_reason']}")
    if analysis.get("formations"):
        st.write(f"**{analysis.get('bet_type','')}:**")
        for f in analysis["formations"]: st.code(f,language=None)

    # ── 買い目 ──
    if analysis.get("bets"):
        st.markdown("#### 💰 期待値判定（買い目候補）")
        rank_labels = [f'{r["course"]}C{r.get("name","")}' for r in scored[:3]]
        st.caption(f"📊 スコア順: {' > '.join(rank_labels)}")
        bdf=pd.DataFrame([{"分類":b["note"],"買い目":b["bet"],"的中率":f'{b["hit_rate"]*100:.2f}%',"必要倍率":f'{b["req_odds"]:.1f}倍以上'} for b in analysis["bets"]])
        st.dataframe(bdf,use_container_width=True,hide_index=True)
        st.caption("💡 期待値=想定的中率×実オッズ。実オッズが「必要倍率」以上なら期待値1.0超。")

    # ── デバッグ ──
    with st.expander("🔧 デバッグ情報"):
        st.write("**boatrace-db.net 取得結果:**")
        st.write(f"- 節間データ: {len(db_data.get('session',{}))}艇分取得")
        st.write(f"- 3連単: {db_data.get('trifecta','-')} / ¥{db_data.get('trifecta_payout',0):,}")
        if db_data.get("debug"): st.write(f"- エラー: {db_data['debug']}")
        st.write(f"**コース別成績:** {len(course_stats_map)}選手分取得")
        if db_data.get("raw"):
            st.text_area("boatrace-db.net 生テキスト(先頭3000字)", db_data["raw"], height=200)

    st.markdown("---")
    st.caption("※AI予想は参考情報です。購入は自己判断・自己責任で。\n※1日最大5レース/1レース投資上限25%推奨。")


if __name__=="__main__":
    main()
