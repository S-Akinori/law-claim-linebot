# utils_compensation.py
from db import supabase

# ユーザー回答から慰謝料を算出する共通関数
def calculate_compensation(user_id: str, account_id: str, compensation_table_id: str) -> int:
    # 1. 対象の慰謝料テーブルを取得
    table_res = supabase.table("compensation_tables").select("table_name").eq("id", compensation_table_id).single().execute()
    if not table_res.data:
        return 0
    table_name = table_res.data["table_name"]

    # 2. この表に必要な kind（通院月数など）と質問IDのマッピングを取得
    mappings = supabase.table("compensation_input_mapping").select("kind, question_id")\
        .eq("compensation_table_id", compensation_table_id).execute().data
        
    # 3. ユーザーの回答を kind ごとに取得（すべて int で扱える前提）
    conditions = {}
    for m in mappings:
        res = supabase.table("user_responses").select("response").eq("account_id", account_id)\
            .eq("user_id", user_id).eq("question_id", m["question_id"]).execute()
        if res.data:
            try:
                conditions[m["kind"]] = int(res.data[0]["response"])
            except ValueError:
                continue
    

    # 4. 対応する慰謝料テーブルから完全一致で検索
    query = supabase.table(table_name).select("amount")
    for key, val in conditions.items():
        if key == "hospitalization_months" or key == "outpatient_months":
            query = query.eq(key, val//30)
        else:
            query = query.eq(key, val)
    result = query.limit(1).execute()
    print(result)

    return result.data[0]["amount"] if result.data else 0


# テスト用: "計算結果" と送られたときに慰謝料結果を返信
from linebot.models import TextSendMessage

def handle_calculation_request(user_id: str, account: dict, line_bot_api, reply_token):
    compensation_table_id = "ee9d7550-d992-44df-8409-8cbd2ab58912"
    if not compensation_table_id:
        line_bot_api.reply_message(reply_token, TextSendMessage(text="計算用の慰謝料テーブルが設定されていません。"))
        return

    amount = calculate_compensation(user_id, account["id"], compensation_table_id)
    if amount:
        text = f"あなたの慰謝料の目安は {amount:,} 円です。"
    else:
        text = "必要な情報が不足しているため、慰謝料を計算できませんでした。"

    line_bot_api.reply_message(reply_token, TextSendMessage(text=text))
