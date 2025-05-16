
from linebot.models import *
import os
from db import supabase
from utils import (
    get_or_create_line_user,
    upsert_line_user,
)
from utils_master import (
    get_master_question,
    get_master_options,
    get_master_next_question_id_by_conditions,
    save_master_user_response,
    get_master_user_response_dict,
)
from function.render_teplate import extract_placeholders, render_template, fetch_data_for_template
from ss import client

from function.generate_result_message import generate_result_message
from master.send_master_question_with_image_options import send_master_question_with_image_options
from function.send_message import send_final_email
from urllib.parse import unquote

async def master_handle_postback(event, account, api, reply_token):
    line_id = event.source.user_id
    data = dict(pair.split("=", 1) for pair in event.postback.data.split("&"))
    option_id = data.get("option_id")
    question_id = data.get("question_id")
    response = unquote(data.get("response", ""))
    
    profile = api.get_profile(line_id)
    display_name = profile.display_name
    
    spreadsheet = client.open_by_key(account["sheet_id"])
    user_sheet = spreadsheet.worksheet("user_list")
    
    user = get_or_create_line_user(line_id, account["id"], display_name, user_sheet)
    
    user_id = user["id"]
    
    question = get_master_question(account["id"], question_id)

    save_master_user_response(user_id, account["id"], question_id, option_id, response, key=question["key"], sheet=user_sheet)
    upsert_line_user(user_id, question_id)

    next_qid = get_master_next_question_id_by_conditions(question_id, user_id)
    master_actions_res = supabase.table("master_actions").select("*").eq("next_master_question_id", next_qid).execute()
    master_actions_data = master_actions_res.data[0] if master_actions_res.data else None

    if master_actions_data and master_actions_data["type"] == "complete_notification":
        send_final_email(user_id, account, master_actions_data["master_email_template_id"])
        supabase.table("line_users").update({"is_answer_complete": True}).eq("id", user_id).execute()
    
    if master_actions_data and master_actions_data["type"] == "calculation":
        responses = get_master_user_response_dict(user_id)
    
        text = generate_result_message(responses)
                    
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