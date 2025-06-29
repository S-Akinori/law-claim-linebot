from fastapi import APIRouter
from db import supabase
import logging

from utils import (
    get_email_template,
    send_email_via_mailtrap
)
from utils_master import (
    get_master_email_template,
)

# ログ設定
logging.basicConfig(level=logging.INFO)

router = APIRouter()

@router.get("/not-complete-messages/send")
async def send_not_complete_messages():
        
    # アカウントごとに処理
    accounts_res = supabase.table("accounts").select("*").execute()
    accounts = accounts_res.data if accounts_res.data else []
    
    action_res = supabase.table("master_actions").select("*").eq("type", "incomplete_notification").execute()
    action_data = action_res.data[0] if action_res.data else None
    
    mail_template_id_key = "master_email_template_id"
    
    for account in accounts:
        account_id = account["id"]
        use_master = account["use_master"]
        
        # 対象ユーザー取得（回答未完了のみかつメール通知をしていない）
        users_res = supabase.table("line_users").select("*").eq("account_id", account_id).eq("is_answer_complete", False).eq('is_email_sent', False).execute()

        if not users_res.data:
            continue
        
        if not use_master :
            action_res = supabase.table("actions").select("*").eq("account_id", account_id).eq("type", "incomplete_notification").execute()
            action_data = action_res.data[0] if action_res.data else None
            mail_template_id_key = "email_template_id"
            
        
        for user in users_res.data:
            user_id = user["id"]

            # 送信済みチェック
            sent_res = supabase.table("line_users").select("is_email_sent").eq("id", user_id).execute()
            is_sent = sent_res.data[0]["is_email_sent"] if sent_res.data else False
            
            if not is_sent:
                send_template_email(user_id, account, action_data[mail_template_id_key])
                
                # 送信済記録
                supabase.table("line_users").update({"is_email_sent": True}).eq("id", user_id).execute()

    return {"status": "done"}

import re

def send_template_email(user_id: str, account: dict, email_template_id: str):
    template = None
    if account["use_master"] :
        template = get_master_email_template(email_template_id)
    else:
        template = get_email_template(email_template_id)
        
    
    main_email = account["email"]
    sub_emails = account["sub_emails"]
    to_emails = []
    if main_email:
        to_emails.append(main_email)
    if sub_emails: 
        for email in sub_emails:
            to_emails.append(email)
    
    if not main_email:
        return

    subject = render_template_with_answers(template["subject"], user_id, account)
    body = render_template_with_answers(template["body"], user_id, account)
    
    for to_email in to_emails:
        send_email_via_mailtrap(to_email, subject, body)

def render_template_with_answers(template: str, user_id: str, account) -> str:
    pattern = r"\{answer:([0-9a-fA-F\-]{36})\}"
    question_ids = re.findall(pattern, template)
    if not question_ids:
        return template
    
    res = None
    response_map = {}
    
    if account["use_master"] :
        res = supabase.table("user_responses").select("master_question_id, response").eq("user_id", user_id).in_("master_question_id", question_ids).execute()
        response_map = {r["master_question_id"]: r["response"] for r in res.data}
    else:
        res = supabase.table("user_responses").select("question_id, response").eq("user_id", user_id).in_("question_id", question_ids).execute()
        response_map = {r["question_id"]: r["response"] for r in res.data}

    def replace(match):
        qid = match.group(1)
        return response_map.get(qid, f"(未回答)")
    
    name_placeholder_pattern = r"\{line_users\.name\}"
    user_res = supabase.table("line_users").select("name").eq("id", user_id).maybe_single().execute()
    user_name = user_res.data["name"] if user_res.data else "(名前未設定)"
    
    template = re.sub(name_placeholder_pattern, user_name, template)

    return re.sub(pattern, replace, template)