from linebot.models import *
from db import supabase
from utils import (
    get_question,
    get_options,
    get_or_create_line_user,
    upsert_line_user,
    save_user_response,
    get_next_question_id_by_conditions,
    get_user_response_dict
)

from function.send_message import send_final_email
from function.render_teplate import extract_placeholders, render_template, fetch_data_for_template

from account.send_question_with_image_options import send_question_with_image_options
from function.generate_result_message import generate_result_message

from ss import client


async def handle_text(event, account, api):
    line_id = event.source.user_id
    text = event.message.text
    reply_token = event.reply_token
    profile = api.get_profile(line_id)
    display_name = profile.display_name
    
    spreadsheet = client.open_by_key(account["sheet_id"])
    user_sheet = spreadsheet.worksheet("user_list")
    
    user = get_or_create_line_user(line_id, account["id"], display_name, user_sheet)
    
    user_id = user["id"]
    account_id = account["id"]

    # トリガー対応（例：キーワードで質問開始）
    start_res = supabase.table("start_triggers").select("question_id").eq("keyword", text).execute()
    if start_res.data:
        question_id = start_res.data[0]["question_id"]
        question = get_question(question_id)
        options = get_options(question_id)
        upsert_line_user(user_id, question_id)

        if options:
            send_question_with_image_options(api, reply_token, question, options, account_id)
        else:
            api.reply_message(reply_token, TextSendMessage(text=question["text"]))
        return
    
    if text == "【診断結果】":
        responses = get_user_response_dict(user_id)
        
        text = generate_result_message(responses)
                    
        messages = [
            TextSendMessage(text=text),
        ]
        api.reply_message(reply_token, messages)
        
        return

    # 通常のテキスト回答
    current_qid = user.get("current_question_id")
    question = get_question(current_qid)
    if current_qid:
        save_user_response(user_id, account["id"], current_qid, response=text, key=question["key"], sheet=user_sheet)
        next_qid = get_next_question_id_by_conditions(account_id, current_qid, user_id)
        
        actions_res = supabase.table("actions").select("*").eq("next_question_id", next_qid).execute()
        actions_data = actions_res.data[0] if actions_res.data else None
        
        if actions_data and actions_data["type"] == "calculation":
            responses = get_user_response_dict(user_id)
            text = generate_result_message(responses, user_id=user_id, sheet=user_sheet)
                        
            next_q = get_question(next_qid)
            options = get_options(next_qid)
            upsert_line_user(user_id, next_qid)
            messages = [
                TextSendMessage(text=text),
                TextSendMessage(text=next_q["text"])
            ]
            if options:
                send_question_with_image_options(api, reply_token, next_q, options, account["id"])
            else:
                api.reply_message(reply_token, messages)
            return
                

        # 今の質問が最後の質問かどうか判定
        if actions_data and actions_data["type"] == "complete_notification":
            send_final_email(user_id, account, actions_data["email_template_id"])
            supabase.table("line_users").update({"is_answer_complete": True}).eq("id", user_id).execute()


        next_q = get_question(next_qid)
        options = get_options(next_qid)
        upsert_line_user(user_id, next_qid)
        if options:
            send_question_with_image_options(api, reply_token, next_q, options, account["id"])
        else:
            placeholders = extract_placeholders(next_q["text"])
            data = fetch_data_for_template(placeholders, account["id"])
            rendered = render_template(next_q["text"], data)
            api.reply_message(reply_token, TextSendMessage(text=rendered))