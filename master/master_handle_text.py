# line_handler.py
from linebot.models import *
import os
from db import supabase
from utils import (
    get_or_create_line_user,
    upsert_line_user,
    send_email_via_mailtrap,
)
from utils_master import (
    get_master_question,
    get_master_options,
    get_master_next_question_id_by_conditions,
    get_master_email_template,
    render_master_template_with_answers,
    save_master_user_response,
    get_master_user_response_dict,
    
)
from urllib.parse import quote
from function.send_message import send_final_email
from function.generate_result_message import generate_result_message
from function.render_teplate import extract_placeholders, render_template, fetch_data_for_template
from master.send_master_question_with_image_options import send_master_question_with_image_options

from ss import client

async def master_handle_text(event, account, api):
    line_id = event.source.user_id
    text = event.message.text
    reply_token = event.reply_token
    profile = api.get_profile(line_id)
    display_name = profile.display_name
    
    spreadsheet = client.open_by_key(account["sheet_id"])
    user_sheet = spreadsheet.worksheet("user_list")
    
    user = get_or_create_line_user(line_id, account["id"], display_name, user_sheet)
    
    user_id = user["id"]

    # トリガー対応（例：キーワードで質問開始）
    start_res = supabase.table("master_start_triggers").select("master_question_id").eq("keyword", text).execute()
    if start_res.data:
        question_id = start_res.data[0]["master_question_id"]
        question = get_master_question(account["id"], question_id)
        options = get_master_options(question_id)
        upsert_line_user(user_id, question_id)

        if options:
            send_master_question_with_image_options(api, reply_token, question, options, account["id"])
        else:
            api.reply_message(reply_token, TextSendMessage(text=question["text"]))
        return
    
    if text == "【診断結果】":
        responses = get_master_user_response_dict(user_id)
        
        text = generate_result_message(responses, user_id=user_id, sheet=user_sheet)
                    
        messages = [
            TextSendMessage(text=text),
        ]
        api.reply_message(reply_token, messages)
        
        return

    # 通常のテキスト回答
    current_qid = user.get("current_question_id")
    question = get_master_question(account["id"], current_qid)
    if current_qid:
        validations = question.get("master_validations", [])
        if validations:
            for validation in validations:
                if validation["type"] == "min":
                    try:
                        min_value = int(validation["value"])
                        if int(text) < min_value:
                            api.reply_message(reply_token, TextSendMessage(text=f"数値は{min_value}以上である必要があります。"))
                            return
                    except ValueError:
                        api.reply_message(reply_token, TextSendMessage(text="数値を入力してください。"))
                        return
                elif validation["type"] == "max":
                    try:
                        max_value = int(validation["value"])
                        if int(text) > max_value:
                            api.reply_message(reply_token, TextSendMessage(text=f"数値は{max_value}以下である必要があります。"))
                            return
                    except ValueError:
                        api.reply_message(reply_token, TextSendMessage(text="数値を入力してください。"))
                        return
            
        save_master_user_response(user_id, account["id"], current_qid, response=text, sheet=user_sheet, key=question["key"])
        next_qid = get_master_next_question_id_by_conditions(current_qid, user_id)
        master_actions_res = supabase.table("master_actions").select("*").eq("next_master_question_id", next_qid).execute()
        master_actions_data = master_actions_res.data[0] if master_actions_res.data else None
        if master_actions_data and master_actions_data["type"] == "calculation":
            responses = get_master_user_response_dict(user_id)
            
            text = generate_result_message(responses, user_id=user_id, sheet=user_sheet)

            next_q = get_master_question(account["id"], next_qid)
            options = get_master_options(next_qid)
            upsert_line_user(user_id, next_qid)
            messages = [
                TextSendMessage(text=text),
                TextSendMessage(text=next_q["text"])
            ]
            if options:
                send_master_question_with_image_options(api, reply_token, next_q, options, account["id"])
            else:
                api.reply_message(reply_token, messages)
            return
                

        # 今の質問が最後の質問かどうか判定
        if master_actions_data and master_actions_data["type"] == "complete_notification":
            send_master_final_email(user_id, account, master_actions_data["master_email_template_id"])
            supabase.table("line_users").update({"is_answer_complete": True}).eq("id", user_id).execute()


        next_q = get_master_question(account["id"], next_qid)
        options = get_master_options(next_qid)
        upsert_line_user(user_id, next_qid)
        if options:
            send_master_question_with_image_options(api, reply_token, next_q, options, account["id"])
        else:
            placeholders = extract_placeholders(next_q["text"])
            data = fetch_data_for_template(placeholders, account["id"])
            rendered = render_template(next_q["text"], data)
            api.reply_message(reply_token, TextSendMessage(text=rendered))
            
def send_master_final_email(user_id: str, account: dict, email_template_id: str):
    template = get_master_email_template(email_template_id)
    # to_email = get_user_answer_response(user_id, account["id"], account["email_answer_question_id"])
    
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

    subject = render_master_template_with_answers(template["subject"], user_id)
    body = render_master_template_with_answers(template["body"], user_id)
    
    for to_email in to_emails:
        send_email_via_mailtrap(to_email, subject, body)
        