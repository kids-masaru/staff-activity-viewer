
import os
import json
from datetime import datetime, date, timedelta
from pathlib import Path
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types


# ... (rest of imports)

# Load environment variables
load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Using Gemini 2.5 Flash
GEMINI_MODEL = "gemini-2.5-flash" 

# Kintone API Configuration
KINTONE_SUBDOMAIN = os.getenv("KINTONE_SUBDOMAIN")
KINTONE_APP_ID = os.getenv("KINTONE_APP_ID")
KINTONE_API_TOKEN = os.getenv("KINTONE_API_TOKEN")
KINTONE_CLIENT_APP_ID = os.getenv("KINTONE_CLIENT_APP_ID")
KINTONE_CLIENT_API_TOKEN = os.getenv("KINTONE_CLIENT_API_TOKEN")

SAVED_AUDIO_DIR = Path("./saved_audio")

# =============================================================================
# MASTER DATA
# =============================================================================

SALES_ACTIVITY_OPTIONS = [
    "架電、メール", "アポ架電（担当者通電）", "初回訪問", "提案（担当者訪問）", 
    "提案（見積書提出）", "提案（決裁者訪問・プレゼン）", "合意後訪問（商談）", 
    "訪問（公示前）", "公示対応（提案書提出）", "公示対応（プレゼン参加）", 
    "公示対応（入札・開封）", "合意後訪問（公示）",
]

NEXT_SALES_ACTIVITY_OPTIONS = [
    "架電、メール", "アポ架電（担当者通電）", "提案（初回訪問）", "提案（担当者訪問）",
    "提案（見積書提出）", "提案（決裁者訪問・プレゼン）", "合意後訪問（商談）",
    "提案（公示前）", "公示対応（提案書提出）", "公示対応（プレゼン参加）",
    "公示対応（入札・開封）", "合意後訪問（公示）",
]

STAFF_OPTIONS = [
    "水野 邦彦", "杉山 拓真", "一條 祐輔", "堀越 隆太郎", "矢部 昌子", 
    "鈴木 沙耶佳", "井﨑 優", "鈴木 智朗", "中村 紀夫",
]

STAFF_CODE_MAP = {
    "水野 邦彦": "mizuno.k@kids-21.co.jp",
    "杉山 拓真": "sugiyama.t@kids-21.co.jp",
    "一條 祐輔": "ichijo.y@kids-21.co.jp",
    "堀越 隆太郎": "horikoshi.r@kids-21.co.jp",
    "矢部 昌子": "yabe.m@kids-21.co.jp",
    "鈴木 沙耶佳": "suzuki.sayaka@kids-21.co.jp",
    "井﨑 優": "izaki.m@kids-21.co.jp",
    "鈴木 智朗": "suzuki.tomoaki@kids-21.co.jp",
    "中村 紀夫": "nakamura.norio@kids-21.co.jp",
}

# =============================================================================
# FUNCTIONS
# =============================================================================

def init_directories():
    SAVED_AUDIO_DIR.mkdir(exist_ok=True)

def init_gemini():
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY が設定されていません。")
        return False
    return True

def save_audio_file(uploaded_file) -> str:
    init_directories()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Use .filename for the original filename, .name is the form field name
    filename_attr = getattr(uploaded_file, 'filename', uploaded_file.name)
    extension = Path(filename_attr).suffix
    if not extension:
        extension = ".mp3"
    # Safe filename (timestamp only) to avoid UnicodeEncodeError during SDK upload
    filename = f"{timestamp}{extension}"
    file_path = SAVED_AUDIO_DIR / filename
    
    # Use .save() for FileStorage objects (Flask/Werkzeug)
    if hasattr(uploaded_file, 'save'):
        uploaded_file.save(str(file_path))
    else:
        # Fallback for BytesIO or other objects (e.g. testing)
        with open(file_path, "wb") as f:
            if hasattr(uploaded_file, 'getbuffer'):
                f.write(uploaded_file.getbuffer())
            elif hasattr(uploaded_file, 'read'):
                uploaded_file.seek(0)
                f.write(uploaded_file.read())
            elif hasattr(uploaded_file, 'getvalue'):
                f.write(uploaded_file.getvalue())
                
    return str(file_path)

def convert_date_str_safe(date_str: str, default_func=None) -> date:
    try:
        if not date_str: raise ValueError
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        return default_func() if default_func else date.today()

def search_clients(keyword: str) -> list:
    if not KINTONE_CLIENT_APP_ID or not KINTONE_CLIENT_API_TOKEN:
        print("取引先アプリの設定が不足しています。")
        return []
    url = f"https://{KINTONE_SUBDOMAIN}.cybozu.com/k/v1/records.json"
    headers = {"X-Cybozu-API-Token": KINTONE_CLIENT_API_TOKEN}
    params = {"app": KINTONE_CLIENT_APP_ID, "query": f'取引先名 like "{keyword}" limit 20'}
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200: return []
        records = response.json().get("records", [])
        return [{
            "id": rec.get("取引先ID", {}).get("value", rec["$id"]["value"]),
            "record_id": rec["$id"]["value"],
            "name": rec.get("取引先名", {}).get("value", "不明")
        } for rec in records]
    except: return []

def get_current_date_str():
    return datetime.now().strftime("%Y-%m-%d")

def calculate_smart_next_date(base_date_str: str) -> str:
    """
    3日後を計算。土日なら翌月曜日までスキップする。
    """
    try:
        if not base_date_str: base = date.today()
        else: base = datetime.strptime(base_date_str, "%Y-%m-%d").date()
    except:
        base = date.today()
        
    # 3日後
    target = base + timedelta(days=3)
    
    # 曜日チェック (0=Mon, 6=Sun). 5=Sat, 6=Sun
    # 土曜(5)なら+2日(月曜), 日曜(6)なら+1日(月曜)
    if target.weekday() == 5: # Sat
        target += timedelta(days=2)
    elif target.weekday() == 6: # Sun
        target += timedelta(days=1)
        
    return target.strftime("%Y-%m-%d")

def get_extraction_prompt(current_date_str: str):
    # f-stringでのJSON出力には {{ }} でのエスケープが必要です
    return f"""
あなたは営業報告書作成のエキスパートAIです。
入力された商談の文字起こしやメモ情報から、以下のフィールドを厳密なJSON形式で抽出してください。

## 前提条件
- **現在日時**: {current_date_str}
- **自社名**: 株式会社キッズコーポレーション（通称：キッズ、キッズさん 等）
- 自社の情報は「競合情報」には含めず、必要な場合のみ「商談内容」に含めてください。
- 入力テキストには誤字・脱字の可能性があります。文脈から補完してください。
- **敬称の厳格ルール**:
    - **「氏」は絶対に使用しないでください。**
    - **クライアント（相手方）の担当者名には必ず「様」をつけてください。**
    - 自社メンバーや身内には敬称（様、氏、さん）をつけないでください（呼び捨て）。

## フィールド抽出ルール

### 1. 新規営業件名 (sales_activity_type)
**重要: 訪問か架電かの判定ロジック**
- **音声データがある場合**: 原則として「**訪問**」系（初回訪問、提案、合意後訪問など）とみなしてください。
- **テキストのみの場合**: 文脈から判断してください。
    - 「伺いました」「訪問し」「対面で」「名刺交換」「オフィスの様子」等の記述 -> **訪問**
    - 「お電話にて」「架電」「不在」等の記述 -> **架電、メール**
    - 明確なキーワードがない場合も、商談の深さ（見積提示など）から推測してください。

[選択肢]: "架電、メール", "アポ架電（担当者通電）", "初回訪問", "提案（担当者訪問）", "提案（見積書提出）", "提案（決裁者訪問・プレゼン）", "合意後訪問（商談）", "訪問（公示前）", "公示対応（提案書提出）", "公示対応（プレゼン参加）", "公示対応（入札・開封）", "合意後訪問（公示）"

### 2. 対応日 (action_date)
活動日付 (YYYY-MM-DD)。不明時は本日({current_date_str})。

### 3. 現在の課題・問題点 (current_issues)
**文体指定: 常体（〜だ、〜である）で統一。「〜しました」「〜です」は禁止。**
- 内容: クライアントの悩み、困りごと。(100〜200文字)
- **重要: 情報がない場合は、必ず空欄（空文字列 ""）にしてください。「特になし」「不明」等の記載は禁止。**
- **抽出対象例**:
  - 園児が集まらない、利用率が低い
  - 保育士の反発、採用難、退職
  - 委託会社と連絡が取れない、対応が悪い
  - 予算超過、コスト高、運営の手間
  - 制度への理解不足、監査対応の負担

### 4. 競合・マーケット情報 (competitor_market_info)
**文体指定: 常体（〜だ、〜である）で統一。「〜しました」「〜です」は禁止。**
- **重要: 「競合他社の具体的な情報」のみを抽出してください。一般的な保育業界のニュースや市場動向は不要です。**
- **情報がない場合は、必ず空欄（空文字列 ""）にしてください。「不明」「特になし」等の記載は禁止。**
- **抽出対象**:
  - 競合の名前（アンフィニ、IQキッズ、スクルド等）
  - **価格・契約条件**: 委託費、現在の契約金額、値引き情報など
  - **弱点・課題**: 競合に対する不満（「連絡が遅い」「質が悪い」「値上げされた」等）
  - **動き**: 営業攻勢、撤退の噂、新規提案の内容
- **注意**: 自社の情報は含めないこと。

### 5. 商談内容 (meeting_summary)
**文体指定: 常体（〜だ、〜である）で統一。「〜しました」「〜です」は禁止。**
**重要: 重複排除ルール**
- **「現在の課題」「競合・マーケット情報」に記載した内容は、ここには絶対に記載しないでください。**
- 上記2項目に含まれない、その他の会話内容、実施した具体的なアクション、相手の反応、事実関係のみを記載してください。
**重要: フォーマットと改行**
- **冒頭の担当者記載**: 相手方の担当者や役職が特定できる場合は、**必ず1行目に「役職：名前様」の形式で記載し、改行してください。**
    - 例: `代表取締役：堤様`
    - 例: `総務部：松本様`
- **読みやすさ**: 話題が変わる際や、冒頭の担当者名の後には、適切に改行を入れて読みやすくしてください（詰め込みすぎない）。
- **構成**:
  1. **担当者情報**（判明している場合のみ冒頭に記載） 
  2. **訪問種類の明記**:（例：初回訪問を実施した、等）
  3. **実施内容と反応**: 何を説明し、どういう反応だったか事実のみ。
  4. **園の基本情報**: 園児数、先生人数、駐車場契約、園種別などがあれば必ず記載。
- 記述例: 
    ```
    代表取締役：堤様

    初回飛び込み訪問を実施した。園児数は0歳1名...
    ```

### 6. 次回提案内容 (next_proposal)
- 次に行うべき「具体的なアクション」を簡潔に。(50文字以内)
- 抽象的な表現（「関係構築に努める」等）は避け、行動ベースで記載してください。
- **記述例**:
  - 定期的に連絡を行う
  - 不在だったため、日時を改めて架電する
  - 見積書を作成し、アポイント取得の連絡をする
  - ○月○日に再訪問する

### 7. 次回提案予定日 (next_proposal_date)
- **重要: 会話やメモに含まれる具体的な日付指示を優先抽出してください。**
- 「明日」「明後日」「来週の月曜」「14日」などの発言がある場合、現在日時({current_date_str})を基準に具体的な日付(YYYY-MM-DD)を計算して入力してください。
- 具体的な指定がない場合は、空欄（""）にしてください。

### 8. 次回営業件名 (next_sales_activity_type)
次回提案内容に合致する選択肢。不明時は空欄。
[選択肢]: {", ".join(f'"{opt}"' for opt in NEXT_SALES_ACTIVITY_OPTIONS)}

## 出力形式
```json
{{
    "新規営業件名": "選択肢から選択",
    "対応日": "YYYY-MM-DD",
    "商談内容": "...",
    "現在の課題・問題点": "...",
    "競合・マーケット情報": "...",
    "次回提案内容": "...",
    "次回提案予定日": "YYYY-MM-DD",
    "次回営業件名": "選択肢から選択"
}}
```
"""

def get_qa_extraction_prompt(current_date_str: str):
    return f"""
あなたは議事録作成のエキスパートAIです。
入力された商談の文字起こしやメモ情報から、以下のフィールドを厳密なJSON形式で抽出してください。

## 目的
商談の中で行われた「質疑応答（Q&A）」を抽出し、ナレッジとして蓄積するため。

## 前提条件
- **現在日時**: {current_date_str}
- **自社名**: 株式会社キッズコーポレーション

## フィールド抽出ルール

### 1. 質疑応答リスト (qa_list)
- 商談の中でクライアントから出た「質問」と、それに対する自社の「回答」をペアで抽出してください。
- 挨拶や雑談は除外し、業務に関連する内容のみ抽出してください。
- **構成**:
  - question: 相手からの質問、疑問、確認事項
  - answer: こちらの回答、説明内容

## 出力形式
```json
{{
    "qa_list": [
        {{
            "question": "...",
            "answer": "..."
        }},
        ...
    ]
}}
```
"""

def parse_json_response(response_text: str) -> dict:
    try:
        if "```json" in response_text: json_str = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text: json_str = response_text.split("```")[1].split("```")[0].strip()
        else: json_str = response_text.strip()
        import re
        json_str = re.sub(r':\s*"([^"]*)"', lambda m: ': "' + m.group(1).replace('\n', '\\n').replace('\r', '') + '"', json_str)
        return json.loads(json_str)
    except: return None

def get_mime_type(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext == ".mp3": return "audio/mp3"
    elif ext == ".wav": return "audio/wav"
    elif ext == ".m4a": return "audio/mp4" # Gemini usually treats m4a as mp4 audio or just audio/m4a if supported, generally audio/mp4 is safe standard or audio/mpeg
    elif ext == ".webm": return "audio/webm"
    elif ext == ".aac": return "audio/aac"
    elif ext == ".flac": return "audio/flac"
    elif ext == ".ogg": return "audio/ogg"
    elif ext == ".pdf": return "application/pdf"
    elif ext == ".txt": return "text/plain"
    elif ext == ".csv": return "text/csv"
    else: return "audio/mp3" # Fallback

def process_file(source_file_path: str, mode: str = "sales") -> dict:
    if not GEMINI_API_KEY: return {}
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt_func = get_qa_extraction_prompt if mode == "qa" else get_extraction_prompt
    sys_instruct = prompt_func(get_current_date_str())
    
    # Upload file
    mime = get_mime_type(source_file_path)
    print(f"Uploading file: {source_file_path} with mime_type: {mime}")
    
    uploaded_file = client.files.upload(
        file=source_file_path, 
        config={'mime_type': mime}
    )
    
    prompt = "このファイルの内容を分析し、データを抽出してください。"
    
    # Generate
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[uploaded_file, prompt],
        config=types.GenerateContentConfig(system_instruction=sys_instruct)
    )
    return parse_json_response(response.text)

def process_text_only(text: str, mode: str = "sales") -> dict:
    if not GEMINI_API_KEY: return {}
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt_func = get_qa_extraction_prompt if mode == "qa" else get_extraction_prompt
    sys_instruct = prompt_func(get_current_date_str())
    
    prompt = f"以下のテキストからデータを抽出してください:\n\n{text}"
    
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=sys_instruct)
    )
    return parse_json_response(response.text)

def process_file_and_text(source_file_path: str, text: str, mode: str = "sales") -> dict:
    if not GEMINI_API_KEY: return {}
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt_func = get_qa_extraction_prompt if mode == "qa" else get_extraction_prompt
    sys_instruct = prompt_func(get_current_date_str())
    
    mime = get_mime_type(source_file_path)
    print(f"Uploading file: {source_file_path} with mime_type: {mime}")
    
    uploaded_file = client.files.upload(
        file=source_file_path, 
        config={'mime_type': mime}
    )
    
    prompt = f"ファイルの内容を分析し、データを抽出してください。テキストメモ優先:\n{text}"
    
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[uploaded_file, prompt],
        config=types.GenerateContentConfig(system_instruction=sys_instruct)
    )
    return parse_json_response(response.text)

def sanitize_text(text: str) -> str:
    if not text: return ""
    import re
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', str(text)).strip()

def upload_file_to_kintone(file_path: str, file_name: str) -> str:
    if not all([KINTONE_SUBDOMAIN, KINTONE_API_TOKEN]): return ""
    url = f"https://{KINTONE_SUBDOMAIN}.cybozu.com/k/v1/file.json"
    headers = {"X-Cybozu-API-Token": KINTONE_API_TOKEN}
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_name, f)}
            response = requests.post(url, headers=headers, files=files)
            response.raise_for_status()
            return response.json().get("fileKey", "")
    except Exception as e:
        print(f"ファイルアップロードエラー: {e}")
        return ""

def upload_to_kintone(data: dict, file_keys: list = None) -> bool:
    if not all([KINTONE_SUBDOMAIN, KINTONE_APP_ID, KINTONE_API_TOKEN]): return False
    url = f"https://{KINTONE_SUBDOMAIN}.cybozu.com/k/v1/record.json"
    combined_token = KINTONE_API_TOKEN
    if KINTONE_CLIENT_API_TOKEN: combined_token = f"{KINTONE_API_TOKEN},{KINTONE_CLIENT_API_TOKEN}"
    headers = {"X-Cybozu-API-Token": combined_token, "Content-Type": "application/json; charset=utf-8"}
    
    staff_name = data.get("対応者", "")
    staff_code = STAFF_CODE_MAP.get(staff_name, "")
    
    record = {
        "取引先ID": {"value": str(data.get("取引先ID", ""))},
        "新規営業件名": {"value": sanitize_text(data.get("新規営業件名", ""))},
        "対応日": {"value": sanitize_text(data.get("対応日", ""))},
        "対応者": {"value": [{"code": staff_code}] if staff_code else []},
        "商談内容": {"value": sanitize_text(data.get("商談内容", ""))},
        "現在の課題・問題点": {"value": sanitize_text(data.get("現在の課題・問題点", ""))},
        "競合・マーケット情報": {"value": sanitize_text(data.get("競合・マーケット情報", ""))},
        "次回提案内容": {"value": sanitize_text(data.get("次回提案内容", ""))},
        "次回提案予定日": {"value": sanitize_text(data.get("次回提案予定日", ""))},
        "次回営業件名": {"value": sanitize_text(data.get("次回営業件名", ""))},
    }
    if file_keys: record["添付ファイル_0"] = {"value": [{"fileKey": fk} for fk in file_keys]}
    
    payload = {"app": int(KINTONE_APP_ID), "record": record}
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        resp.raise_for_status()
        return True, ""
    except Exception as e:
        error_msg = f"{str(e)}"
        try:
            if 'resp' in locals():
                error_msg += f" Response: {resp.text}"
        except:
            pass
        print(f"Kintone Error: {error_msg}")
        return False, error_msg

def fetch_client_history(client_id: str, limit: int = 5) -> list:
    """
    Fetch recent sales reports for a specific client.
    """
    if not all([KINTONE_SUBDOMAIN, KINTONE_APP_ID, KINTONE_API_TOKEN]): return []
    
    url = f"https://{KINTONE_SUBDOMAIN}.cybozu.com/k/v1/records.json"
    combined_token = KINTONE_API_TOKEN
    if KINTONE_CLIENT_API_TOKEN: combined_token = f"{KINTONE_API_TOKEN},{KINTONE_CLIENT_API_TOKEN}"
    headers = {"X-Cybozu-API-Token": combined_token}
    
    # Query: Match ClientID, Order by Date Desc
    query = f'取引先ID = "{client_id}" order by 対応日 desc limit {limit}'
    params = {"app": KINTONE_APP_ID, "query": query}
    
    try:
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"History Fetch Error: {resp.text}")
            return []
            
        records = resp.json().get("records", [])
        history = []
        for r in records:
            history.append({
                "date": r.get("対応日", {}).get("value", ""),
                "staff": r.get("対応者", {}).get("value", [{}])[0].get("name", "") if r.get("対応者", {}).get("value") else "",
                "type": r.get("新規営業件名", {}).get("value", ""),
                "content": r.get("商談内容", {}).get("value", ""),
                "next_action": r.get("次回提案内容", {}).get("value", "")
            })
        return history
    except Exception as e:
        print(f"History Fetch Exception: {e}")
        return []

def summarize_history(history_data: list) -> dict:
    """
    Use Gemini to summarize the history list.
    """
    if not history_data or not GEMINI_API_KEY:
        return {"summary": "履歴がありません。", "latest": ""}
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Construct context txt
    context_text = ""
    for i, item in enumerate(history_data):
        context_text += f"[{item['date']}] {item['type']} (担当: {item['staff']})\n"
        context_text += f"内容: {item['content']}\n"
        context_text += f"次回: {item['next_action']}\n\n"
        
    prompt = f"""
あなたは営業アシスタントです。以下の過去の商談履歴（直近{len(history_data)}件）を読み、次の訪問に向けた要約を作成してください。

## 履歴データ
{context_text}

## 出力要件 (JSON形式)
- **flow**: これまでの経緯や主な議論の流れを「3行程度」で簡潔にまとめてください。
- **latest_status**: 直近の商談で何が決まり、今はどういう状態か（次に何をする予定か）を「1行」でまとめてください。

## 出力例
```json
{{
  "flow": "初回訪問でニーズをヒアリングし、見積を提示したが価格面で難色を示された。\\nその後、上長同行で再提案を行い、メリットを強調したことで検討フェーズに入った。\\n競合他社との比較表を提出し、優位性をアピールし続けている。",
  "latest_status": "最終見積を提出済みで、来月の決裁会議の結果待ち状態。"
}}
```
"""
    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return parse_json_response(resp.text)
    except Exception as e:
        print(f"Summarize Error: {e}")
        return {"flow": "要約生成に失敗しました。", "latest_status": ""}

# =============================================================================
# STAFF ACTIVITY VIEWER FUNCTIONS
# =============================================================================

def fetch_staff_activities(staff_email: str, start_date: str, end_date: str) -> list:
    """
    Fetch sales activities for a specific staff member within a date range.
    """
    if not all([KINTONE_SUBDOMAIN, KINTONE_APP_ID, KINTONE_API_TOKEN]): 
        return []
    
    url = f"https://{KINTONE_SUBDOMAIN}.cybozu.com/k/v1/records.json"
    combined_token = KINTONE_API_TOKEN
    if KINTONE_CLIENT_API_TOKEN: 
        combined_token = f"{KINTONE_API_TOKEN},{KINTONE_CLIENT_API_TOKEN}"
    headers = {"X-Cybozu-API-Token": combined_token}
    
    # Query: Match staff email, date range, order by date desc - increased limit to 500
    query = f'対応者 in ("{staff_email}") and 対応日 >= "{start_date}" and 対応日 <= "{end_date}" order by 対応日 desc limit 500'
    params = {"app": KINTONE_APP_ID, "query": query}
    
    try:
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"Staff Activities Fetch Error: {resp.text}")
            return []
            
        records = resp.json().get("records", [])
        activities = []
        for r in records:
            # Get client name via lookup or stored field
            client_name = r.get("取引先名", {}).get("value", "")
            if not client_name:
                client_name = r.get("取引先ID", {}).get("value", "不明")
            
            activities.append({
                "date": r.get("対応日", {}).get("value", ""),
                "client_name": client_name,
                "type": r.get("新規営業件名", {}).get("value", ""),
                "content": r.get("商談内容", {}).get("value", ""),
                "issues": r.get("現在の課題・問題点", {}).get("value", ""),
                "next_action": r.get("次回提案内容", {}).get("value", ""),
                "next_date": r.get("次回提案予定日", {}).get("value", "")
            })
        return activities
    except Exception as e:
        print(f"Staff Activities Fetch Exception: {e}")
        return []

def filter_mass_emails(activities: list, threshold: int = 10, similarity_ratio: float = 0.90) -> tuple:
    """
    Detect and separate mass emails from individual activities using text similarity.
    Returns: (individual_activities, mass_email_count)
    
    Mass email detection: Activities with 90%+ similar content are grouped together.
    If a group has 10+ items, they are considered mass emails.
    """
    from difflib import SequenceMatcher
    
    if not activities:
        return [], 0
    
    # Calculate similarity between two texts
    def get_similarity(text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        # Use first 200 chars for efficiency
        t1 = text1[:200].strip()
        t2 = text2[:200].strip()
        if not t1 or not t2:
            return 0.0
        return SequenceMatcher(None, t1, t2).ratio()
    
    # Group similar activities
    groups = []  # List of lists of indices
    assigned = set()
    
    for i, activity_i in enumerate(activities):
        if i in assigned:
            continue
            
        content_i = activity_i.get("content", "")
        if not content_i or len(content_i.strip()) < 20:
            # Too short to be mass email, skip
            continue
            
        group = [i]
        assigned.add(i)
        
        for j, activity_j in enumerate(activities):
            if j in assigned or j <= i:
                continue
                
            content_j = activity_j.get("content", "")
            if not content_j:
                continue
                
            # Check similarity
            if get_similarity(content_i, content_j) >= similarity_ratio:
                group.append(j)
                assigned.add(j)
        
        if len(group) >= threshold:
            groups.append(group)
    
    # Collect all mass email indices
    mass_email_indices = set()
    for group in groups:
        mass_email_indices.update(group)
    
    # Separate activities
    individual_activities = []
    for i, activity in enumerate(activities):
        if i not in mass_email_indices:
            individual_activities.append(activity)
    
    mass_email_count = len(mass_email_indices)
    
    return individual_activities, mass_email_count

def count_activities_by_type(activities: list) -> dict:
    """
    Count activities grouped by type (新規営業件名).
    Returns a dict like {"架電、メール": 5, "初回訪問": 2, ...}
    """
    counts = {}
    for a in activities:
        activity_type = a.get("type", "その他")
        if not activity_type:
            activity_type = "その他"
        counts[activity_type] = counts.get(activity_type, 0) + 1
    return counts

def summarize_staff_activities(activities: list, staff_name: str, start_date: str, end_date: str) -> dict:
    """
    Use Gemini to summarize staff activities for the period.
    """
    if not activities or not GEMINI_API_KEY:
        return {"flow": "活動記録がありません。", "highlights": "", "concerns": ""}
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Construct context text
    context_text = ""
    for i, item in enumerate(activities[:20]):  # Limit to 20 for context length
        context_text += f"[{item['date']}] {item['type']} - {item['client_name']}\n"
        if item['content']:
            content_preview = item['content'][:200] + "..." if len(item['content']) > 200 else item['content']
            context_text += f"  内容: {content_preview}\n"
        if item['next_action']:
            context_text += f"  次回: {item['next_action']}\n"
        context_text += "\n"
        
    prompt = f"""
あなたはマネージャー向けの営業レポートAIです。以下は{staff_name}さんの{start_date}〜{end_date}の営業活動記録（{len(activities)}件、個別対応のみ）です。

## 活動データ
{context_text}

## 出力要件 (JSON形式)
マネージャーが部下の活動を素早く把握できるよう、以下を作成してください。

### summary（5〜8行で詳しく）
この期間の活動の全体像を**具体的に**まとめてください。
- どのクライアントにどんなアプローチをしているか
- 進行中の案件の状況
- 営業活動の傾向（新規開拓/既存フォロー/提案活動など）
→ マネージャーが読んで「なるほど、こういう動きをしているのか」とわかる厚みのある内容にしてください。

**重要**: 一斉メールや関係性構築メールの件数には絶対に触れないでください。それは別途システムで表示します。summaryでは個別の商談・提案活動のみに焦点を当ててください。

### highlights（クライアント名を【】で囲む形式）
特に良かった点、成果が出そうな商談を**2〜3社**ピックアップ。
フォーマット例:
```
【株式会社A】
・初回訪問で好感触、次回決裁者同席の提案予定
・予算規模〇〇万円の案件化の可能性

【B社】
・見積依頼を獲得、契約に向けた具体的な調整中
```

### concerns
気になる点があれば「1〜2点」。特になければ「特になし」。

## 出力例
```json
{{
  "summary": "今週は新規開拓と既存フォローの両面で積極的な活動を展開した。\\n株式会社ライブネクストへのアポ架電では、園の運営状況の詳細なヒアリングに成功し、給食業務委託や採用サポートに対する具体的な関心を引き出せた。\\n社会福祉法人福岡市民生事業連盟とは電子契約の進め方について具体的な調整を進めており、契約締結に向けた最終段階に入っている。\\n国家公務員共済組合連合会 新別府病院とは入札案件の対応を継続中。\\n既存顧客からの問い合わせにも迅速に対応しており、多岐にわたる業務を遂行している。",
  "highlights": "【株式会社ライブネクスト】\\n・アポ架電で園の運営状況について詳細なヒアリングに成功\\n・給食業務委託や採用サポートへの具体的な関心を確認\\n\\n【社会福祉法人福岡市民生事業連盟】\\n・電子契約の進め方について具体的な調整中\\n・契約締結に向けた最終段階",
  "concerns": "特になし"
}}
```
"""
    print(f"[DEBUG] Summarizing activities for {staff_name}, {len(activities)} records")
    print(f"[DEBUG] Using model: {GEMINI_MODEL}")
    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        print(f"[DEBUG] Gemini response received, length: {len(resp.text)}")
        result = parse_json_response(resp.text)
        if result:
            return result
        else:
            return {"summary": f"JSONパース失敗: {resp.text[:300]}", "highlights": "", "concerns": ""}
    except Exception as e:
        import traceback
        error_detail = str(e)
        return {"summary": f"Geminiエラー: {error_detail}", "highlights": "", "concerns": ""}

