# utils.py
import re
import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from db import supabase
from gspread import Spreadsheet, Worksheet
from datetime import datetime

load_dotenv()

# Supabase helpers
def get_account_info(account_id: str):
    res = supabase.table("accounts").select("*").eq("id", account_id).execute()
    return res.data[0] if res.data else None

def get_question(question_id: str):
    res = supabase.table("questions").select("*").eq("id", question_id).execute()
    return res.data[0] if res.data else None

def get_options(question_id: str):
    res = supabase.table("options").select("*").eq("question_id", question_id).execute()
    return res.data

def get_or_create_line_user(line_id: str, account_id: str, display_name: str = None, sheet: Worksheet = None):
    res = supabase.table("line_users").select("*").eq("line_id", line_id).eq("account_id", account_id).execute()
    all_rows = sheet.get_all_values()
    header = all_rows[0]
    rows = all_rows[2:]
    
    id_index = header.index("id") + 1
    line_name_index = header.index("line_name") + 1
    date_index = header.index("date") + 1
    target_row = None
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if res.data:
        for i, row in enumerate(rows, start=3):
            if row[0] == res.data[0]['id']:
                target_row = i
                break
    
        if target_row:
            sheet.update_cell(target_row, line_name_index, display_name)
            sheet.update_cell(target_row, date_index, now_str)
        else:
            sheet.append_row([res.data[0]['id'], display_name, now_str])
        
        return res.data[0]
        
    else:
        inserted = supabase.table("line_users").insert({
            "line_id": line_id,
            "account_id": account_id,
            "name": display_name
        }).execute()
        sheet.append_row([inserted.data[0]['id'], display_name, now_str])
    
        return inserted.data[0] if inserted.data else None



def upsert_line_user(user_id: str, current_question_id: str):
    supabase.table("line_users").update({"current_question_id": current_question_id}).eq("id", user_id).execute()


def save_user_response(user_id: str, account_id: str, question_id: str, option_id: str = None, response: str = None, key: str = None, sheet: Worksheet = None ):
    if option_id and not response:
        opt = supabase.table("options").select("text").eq("id", option_id).execute()
        if opt.data:
            response = opt.data[0]["text"]

    existing = supabase.table("user_responses").select("id").eq("user_id", user_id).eq("question_id", question_id).execute()
    if existing.data:
        supabase.table("user_responses").update({"option_id": option_id, "response": response}).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase.table("user_responses").insert({"user_id": user_id, "account_id": account_id, "question_id": question_id, "option_id": option_id, "response": response}).execute()
        
    # === スプレッドシート処理 ===
    if sheet:
        all_rows = sheet.get_all_values()

        header = all_rows[0]  # 2行目がヘッダー
        user_col_index = header.index("id")
        if key not in header:
            raise ValueError(f"'{key}' カラムが見つかりません")

        key_col_index = header.index(key)

        # 3行目以降で user_id を探す
        for idx, row in enumerate(all_rows[2:], start=3):
            if len(row) > user_col_index and row[user_col_index] == user_id:
                # 対象のセルを更新（1-based）
                sheet.update_cell(idx, key_col_index + 1, response)
                print(f"{user_id} の {key} を更新しました（行 {idx}）")
                return

        print(f"user_id '{user_id}' は見つかりませんでした")
        
def get_next_question_id_by_conditions(account_id: str, from_question_id: str, user_id: str):
    routes_res = supabase.table("question_routes").select("*").eq("account_id", account_id).eq("from_question_id", from_question_id).execute()
    routes = routes_res.data

    for route in routes:
        group = route["condition_group"]
        cond_res = supabase.table("conditions").select("*").eq("account_id", account_id).eq("condition_group", group).execute()
        conditions = cond_res.data
        all_match = True
        if not conditions:
            return route["next_question_id"]
        for cond in conditions:
            ans_res = supabase.table("user_responses").select("*").eq("user_id", user_id).eq("question_id", cond["required_question_id"]).execute()
            if not ans_res.data:
                break
            ans = ans_res.data[0]
            if cond["required_option_id"] and cond["operator"] == "=" and ans.get("option_id") != cond["required_option_id"]:
                break
            elif cond["value"] is not None and cond["value"] != '' and ans.get("response") is not None:
                val = cond["value"]
                res_val = ans["response"]
                if cond["operator"] == "=" and res_val != val:
                    break
                
            return route["next_question_id"]
    return None

def get_email_template(template_id: str):
    res = supabase.table("email_templates").select("subject, body").eq("id", template_id).execute()
    return res.data[0] if res.data else None

def get_user_answer_response(user_id: str, account_id: str, question_id: str) -> str:
    res = supabase.table("user_responses").select("response").eq("user_id", user_id).eq("question_id", question_id).execute()
    return res.data[0]["response"] if res.data else None

def render_template_with_answers(template: str, user_id: str, account_id: str) -> str:
    pattern = r"\{answer:([0-9a-fA-F\-]{36})\}"
    question_ids = re.findall(pattern, template)
    if not question_ids:
        return template

    res = supabase.table("user_responses").select("question_id, response").eq("user_id", user_id).in_("question_id", question_ids).execute()
    response_map = {r["question_id"]: r["response"] for r in res.data}

    def replace(match):
        qid = match.group(1)
        return response_map.get(qid, f"(未回答)")

    return re.sub(pattern, replace, template)

def send_email_via_mailtrap(to_email: str, subject: str, body: str):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = "no-reply@consolation-money-bot.com"
    msg["To"] = to_email

    with smtplib.SMTP(os.getenv("MAILTRAP_HOST"), int(os.getenv("MAILTRAP_PORT"))) as server:
        # server.starttls()
        server.login(os.getenv("MAILTRAP_USERNAME"), os.getenv("MAILTRAP_PASSWORD"))
        server.send_message(msg)

def get_user_response_dict(user_id: str) -> dict:
    """
    特定ユーザーの user_responses を id: response 形式で取得
    """
    try:
        res = supabase.table("user_responses")\
            .select("*, questions(*)")\
            .eq("user_id", user_id)\
            .not_.is_("question_id", None)\
            .execute()
            
        print( f"res.data: {res.data}")
        if not res.data:
            return {}

        return {item['questions']['key']: item["response"] for item in res.data}

    except Exception as e:
        print(f"エラー: {e}")
        return {}