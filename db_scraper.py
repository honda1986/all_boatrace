"""
boatrace-db.net スクレイピングモジュール
━━━━━━━━━━━━━━━━━━━━━━━━━━━
レース詳細ページから節間成績・レース結果・3連単払戻金を取得
"""

import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}

# boatrace-db.net の場コード（boatrace.jp の jcd と同じ01-24）
# URL: /race/detail/date/{YYYYMMDD}/pid/{XX}/rno/{N}/


def fetch_db_page(url: str) -> str:
    """boatrace-db.net ページ取得"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    return resp.text


def parse_race_detail(html: str) -> dict:
    """
    boatrace-db.net のレース詳細ページを解析。

    戻り値: {
        "racers": {
            1: {  # 艇番
                "number": "5349",
                "name": "宮崎奏磨",
                "class": "B2",
                "session_results": [6, 6, 6, 6, 6],  # 直近の着順（古い順）
                "session_st": [0.25, 0.15, 0.38, 0.20, 0.22],
                "session_courses": [4, 5, 4, 4, 6],
            },
            ...
        },
        "result": {
            "order": [1, 3, 5, 2, 4, 6],  # 1着の艇番, 2着の艇番, ...
            "trifecta": "1-3-5",
            "trifecta_payout": 12345,
        }
    }
    """
    soup = BeautifulSoup(html, "html.parser")
    data = {"racers": {}, "result": {"order": [], "trifecta": "", "trifecta_payout": 0}}
    full_text = soup.get_text(separator="|", strip=True)

    # ━━━ 1. 選手セクションを解析（節間成績） ━━━
    # boatrace-db.net のレース詳細ページでは、各選手のデータが
    # テーブル形式で並んでいる。
    # 構造: 登録番号 | 選手名 | 級別
    #       初日 | 2日目 | 3日目 ...
    #       レース番号行
    #       コース行（背景色＝艇番, 数字＝進入コース）
    #       ST行
    #       (ST順位)行
    #       結果行

    tables = soup.find_all("table")

    for tbl in tables:
        tbl_text = tbl.get_text(separator="|", strip=True)

        # 選手情報テーブルか判定：登録番号(4桁) + 級別(A1/A2/B1/B2)
        reg_match = re.search(r'(\d{4})', tbl_text)
        class_match = re.search(r'(A1|A2|B1|B2)', tbl_text)

        if not reg_match or not class_match:
            continue

        # 選手名を探す
        name_match = re.search(r'([一-龥ぁ-んァ-ヴー]{1,3}\s*[一-龥ぁ-んァ-ヴー]{1,3})', tbl_text)
        name = name_match.group(1).replace(" ", "").replace("　", "") if name_match else ""

        # 「結果」行のデータを取得 - 着順は1-6の数字、Fや転はスキップ
        # テーブル内の全行を走査
        rows = tbl.find_all("tr")

        # 全てのセルテキストを行ごとに収集
        row_data = []
        for row in rows:
            cells = row.find_all(["td", "th"])
            cell_texts = [c.get_text(strip=True) for c in cells]
            row_data.append(cell_texts)

        # 結果行を特定（最終行が結果行のはず）
        # スクリーンショットから: 結果行は [6, 6, 6, 6, 6] のような着順数値
        session_results = []
        session_st = []
        session_courses = []

        for row_cells in row_data:
            # 着順行を検出: 1-6の数字が主体、Fや転も含む可能性
            nums = []
            is_result_row = True
            for cell in row_cells:
                cell_clean = cell.strip()
                if cell_clean.isdigit() and 1 <= int(cell_clean) <= 6:
                    nums.append(int(cell_clean))
                elif cell_clean in ("F", "転", "落", "エ", "欠", "不", "妨", ""):
                    pass  # 特殊結果はスキップ
                elif re.match(r'^\d+R$', cell_clean):
                    is_result_row = False
                    break
                elif cell_clean in ("初日", "2日目", "3日目", "4日目", "5日目", "6日目", "最終日"):
                    is_result_row = False
                    break

            if is_result_row and len(nums) >= 1:
                # 最も多く着順が含まれる行を結果行として採用
                if len(nums) > len(session_results):
                    session_results = nums

            # ST行を検出: .XX の形式
            st_vals = []
            for cell in row_cells:
                cell_clean = cell.strip()
                m = re.match(r'^\.(\d{2})$', cell_clean)
                if m:
                    st_vals.append(float("0." + m.group(1)))
            if len(st_vals) >= 1 and len(st_vals) > len(session_st):
                session_st = st_vals

            # コース行を検出: (X) の形式のセルが複数、またはXの数字のみ
            course_vals = []
            for cell in row_cells:
                cell_clean = cell.strip()
                m = re.match(r'^\((\d)\)$', cell_clean)
                if m:
                    course_vals.append(int(m.group(1)))
            if len(course_vals) >= 1 and len(course_vals) > len(session_courses):
                session_courses = course_vals

        # 結果が取れたら保存（どの艇番かはテーブル出現順＝1-6）
        if session_results:
            # テーブルの出現順で艇番を推定
            boat_num = len(data["racers"]) + 1
            if boat_num <= 6:
                data["racers"][boat_num] = {
                    "number": reg_match.group(1),
                    "name": name,
                    "class": class_match.group(1),
                    "session_results": session_results,
                    "session_st": session_st,
                    "session_courses": session_courses,
                }

    # ━━━ 2. レース結果（着順）を解析 ━━━
    # 結果セクション: "1着 X号艇" のようなパターン、または結果テーブル
    for tbl in tables:
        tbl_text = tbl.get_text(separator="|", strip=True)
        if "1着" in tbl_text or "着順" in tbl_text:
            # 着順の数字を探す
            order = []
            for rank in range(1, 7):
                pat = rf'{rank}着[|]*(\d)'
                m = re.search(pat, tbl_text)
                if m:
                    order.append(int(m.group(1)))
            if len(order) >= 3:
                data["result"]["order"] = order

    # ━━━ 3. 3連単払戻金を解析 ━━━
    for tbl in tables:
        tbl_text = tbl.get_text(separator="|", strip=True)
        if "3連単" in tbl_text:
            # パターン: 3連単|X-Y-Z|XX,XXX円
            m = re.search(r'3連単[|]*(\d[-=]\d[-=]\d)[|]*([\d,]+)円', tbl_text)
            if m:
                data["result"]["trifecta"] = m.group(1).replace("=", "-")
                data["result"]["trifecta_payout"] = int(m.group(2).replace(",", ""))

    # テーブル外テキストからもフォールバック
    if not data["result"]["trifecta"]:
        m = re.search(r'3連単[|\s]*(\d[-=＝ー]\d[-=＝ー]\d)[|\s]*([\d,]+)\s*円', full_text)
        if m:
            data["result"]["trifecta"] = re.sub(r'[=＝ー]', '-', m.group(1))
            data["result"]["trifecta_payout"] = int(m.group(2).replace(",", ""))

    return data


def get_db_race_detail(jcd: str, date_str: str, race_no: int) -> dict:
    """boatrace-db.net からレース詳細を取得"""
    hd = date_str.replace("-", "")
    url = f"https://boatrace-db.net/race/detail/date/{hd}/pid/{jcd}/rno/{race_no}/"
    try:
        html = fetch_db_page(url)
        return parse_race_detail(html)
    except Exception as e:
        return {"racers": {}, "result": {"order": [], "trifecta": "", "trifecta_payout": 0}, "error": str(e)}


# テスト用
if __name__ == "__main__":
    import sys
    # 使い方: python db_scraper.py 01 2026-04-12 5
    jcd = sys.argv[1] if len(sys.argv) > 1 else "01"
    date = sys.argv[2] if len(sys.argv) > 2 else "2026-04-12"
    rno = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    result = get_db_race_detail(jcd, date, rno)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
