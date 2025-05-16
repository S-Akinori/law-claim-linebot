from linebot.models import *
from db import supabase
from utils import (
    get_question,
    get_or_create_line_user,
    upsert_line_user,
    save_user_response,
    get_next_question_id_by_conditions,
    get_user_response_dict,
    get_options
)

from function.send_message import send_final_email
from function.render_teplate import extract_placeholders, render_template, fetch_data_for_template

from account.send_question_with_image_options import send_question_with_image_options
from function.generate_result_message import generate_result_message

from ss import client
from urllib.parse import unquote

async def handle_postback(event, account, api, reply_token):
    line_id = event.source.user_id
    data = dict(pair.split("=", 1) for pair in event.postback.data.split("&"))
    option_id = data.get("option_id")
    question_id = data.get("question_id")
    response = unquote(data.get("response", ""))
    
    account_id = account["id"]
    
    profile = api.get_profile(line_id)
    display_name = profile.display_name
    
    spreadsheet = client.open_by_key(account["sheet_id"])
    user_sheet = spreadsheet.worksheet("user_list")
    
    user = get_or_create_line_user(line_id, account["id"], display_name, user_sheet)
    
    user_id = user["id"]
    
    question = get_question(question_id)

    save_user_response(user_id, account_id, question_id, option_id, response, key=question["key"], sheet=user_sheet)
    upsert_line_user(user_id, question_id)

    next_qid = get_next_question_id_by_conditions(account_id, question_id, user_id)
    print(next_qid)
    actions_res = supabase.table("actions").select("*").eq("next_question_id", next_qid).execute()
    actions_data = actions_res.data[0] if actions_res.data else None

    if actions_data and actions_data["type"] == "complete_notification":
        send_final_email(user_id, account, actions_data["email_template_id"])
        supabase.table("line_users").update({"is_answer_complete": True}).eq("id", user_id).execute()
    
    if actions_data and actions_data["type"] == "calculation":
        responses = get_user_response_dict(user_id)
    
        text = generate_result_message(responses)
                    
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