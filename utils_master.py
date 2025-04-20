# utils.py
import re
import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from db import supabase

load_dotenv()

# Supabase helpers
def get_account_info(account_id: str):
    res = supabase.table("accounts").select("*").eq("id", account_id).execute()
    return res.data[0] if res.data else None

def get_master_question(account_id: str, question_id: str):
    res = supabase.table("master_questions").select("*").eq("id", question_id).execute()
    return res.data[0] if res.data else None

def get_master_options(question_id: str):
    res = supabase.table("master_options").select("*").eq("master_question_id", question_id).execute()
    return res.data

def get_or_create_line_user(line_id: str, account_id: str, display_name: str = None):
    res = supabase.table("line_users").select("*").eq("line_id", line_id).eq("account_id", account_id).execute()
    if res.data:
        return res.data[0]

    inserted = supabase.table("line_users").insert({
        "line_id": line_id,
        "account_id": account_id,
        "name": display_name
    }).execute()

    return inserted.data[0] if inserted.data else None

def upsert_line_user(user_id: str, current_question_id: str):
    supabase.table("line_users").update({"current_question_id": current_question_id}).eq("id", user_id).execute()

def save_master_user_response(user_id: str, account_id: str, question_id: str, option_id: str = None, response: str = None):
    if option_id and not response:
        opt = supabase.table("master_options").select("text").eq("id", option_id).execute()
        if opt.data:
            response = opt.data[0]["text"]

    existing = supabase.table("user_responses").select("id").eq("user_id", user_id).eq("master_question_id", question_id).execute()
    if existing.data:
        supabase.table("user_responses").update({"master_option_id": option_id, "response": response}).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase.table("user_responses").insert({"user_id": user_id, "account_id": account_id, "master_question_id": question_id, "master_option_id": option_id, "response": response}).execute()

def get_master_next_question_id_by_conditions(from_question_id: str, user_id: str):
    routes_res = supabase.table("master_question_routes").select("*").eq("from_master_question_id", from_question_id).execute()
    routes = routes_res.data

    for route in routes:
        group = route["condition_group"]
        cond_res = supabase.table("master_conditions").select("*").eq("condition_group", group).execute()
        conditions = cond_res.data
        all_match = True
        if not conditions:
            return route["next_master_question_id"]
        for cond in conditions:
            ans_res = supabase.table("user_responses").select("*").eq("user_id", user_id).eq("master_question_id", cond["required_master_question_id"]).execute()
            if not ans_res.data:
                break
            ans = ans_res.data[0]
            print(ans.get("master_option_id"), cond["required_master_option_id"], ans.get("response"))
            if cond["required_master_option_id"] and cond["operator"] == "=" and ans.get("master_option_id") != cond["required_master_option_id"]:
                break
            elif cond["value"] is not None and cond["value"] != '' and ans.get("response") is not None:
                val = cond["value"]
                res_val = ans["response"]
                if cond["operator"] == "=" and res_val != val:
                    break
                
            return route["next_master_question_id"]
    return None

def get_master_email_template(template_id: str):
    res = supabase.table("master_email_templates").select("subject, body").eq("id", template_id).execute()
    return res.data[0] if res.data else None

def get_master_user_answer_response(user_id: str, question_id: str) -> str:
    res = supabase.table("user_responses").select("response").eq("user_id", user_id).eq("master_question_id", question_id).execute()
    return res.data[0]["response"] if res.data else None

def render_master_template_with_answers(template: str, user_id: str) -> str:
    pattern = r"\{answer:([0-9a-fA-F\-]{36})\}"
    question_ids = re.findall(pattern, template)
    if not question_ids:
        return template

    res = supabase.table("user_responses").select("master_question_id, response").eq("user_id", user_id).in_("master_question_id", question_ids).execute()
    response_map = {r["master_question_id"]: r["response"] for r in res.data}

    def replace(match):
        qid = match.group(1)
        return response_map.get(qid, f"(未回答:{qid})")

    return re.sub(pattern, replace, template)

def send_email_via_mailtrap(to_email: str, subject: str, body: str):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = "noreply@example.com"
    msg["To"] = to_email

    with smtplib.SMTP(os.getenv("MAILTRAP_HOST"), int(os.getenv("MAILTRAP_PORT"))) as server:
        # server.starttls()
        server.login(os.getenv("MAILTRAP_USERNAME"), os.getenv("MAILTRAP_PASSWORD"))
        server.send_message(msg)



def get_master_user_response_dict(user_id: send_email_via_mailtrap) -> dict:
    """
    特定ユーザーの user_responses を id: response 形式で取得
    """
    try:
        res = supabase.table("user_responses")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()

        if not res.data:
            return {}

        return {item["master_question_id"]: item["response"] for item in res.data}

    except Exception as e:
        print(f"エラー: {e}")
        return {}
    
    