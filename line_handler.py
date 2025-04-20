# line_handler.py
from fastapi import APIRouter, Request, Query
from linebot import LineBotApi, WebhookParser
from linebot.models import *
from dotenv import load_dotenv
import os
from db import supabase
from utils import (
    get_account_info,
    get_question,
    get_options,
    get_or_create_line_user,
    upsert_line_user,
    save_user_response,
    get_next_question_id_by_conditions,
    render_template_with_answers,
    send_email_via_mailtrap,
    get_email_template,
    get_user_answer_response
)
from utils_master import (
    get_master_question,
    get_master_options,
    get_master_next_question_id_by_conditions,
    get_master_email_template,
    render_master_template_with_answers,
    save_master_user_response,
    get_master_user_answer_response,
    get_master_user_response_dict,
    
)
from utils_compensation import handle_calculation_request
from utils_calculate import (
    calculate_injury_compensation,
    calculate_auto_injury_compensation,
    calculate_death_compensation,
    calculate_auto_death_compensation,
    calculate_lost_income,
    calculate_auto_lost_income,
    calculate_disability_compensation,
    calculate_lost_profits,
    calculate_death_lost_profits
)
from urllib.parse import quote
import re
from collections import defaultdict


router = APIRouter()
load_dotenv()

@router.post("/callback")
async def callback(request: Request, account_id: str = Query(...)):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature")

    account = get_account_info(account_id)
    if not account:
        return "Invalid account_id"

    parser = WebhookParser(account["line_channel_secret"])
    line_bot_api = LineBotApi(account["line_channel_access_token"])

    events = parser.parse(body.decode("utf-8"), signature)
    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
            await master_handle_text(event, account, line_bot_api)
            # await handle_text(event, account, line_bot_api)
        elif isinstance(event, PostbackEvent):
            await master_handle_postback(event, account, line_bot_api, event.reply_token)
            # await handle_postback(event, account, line_bot_api, event.reply_token)

    return "OK"

async def master_handle_text(event, account, api):
    line_id = event.source.user_id
    text = event.message.text
    reply_token = event.reply_token
    profile = api.get_profile(line_id)
    display_name = profile.display_name
    
    user = get_or_create_line_user(line_id, account["id"], display_name)
    
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
        
        text = generate_result_message(responses)
                    
        messages = [
            TextSendMessage(text=text),
        ]
        api.reply_message(reply_token, messages)
        
        return

    # 通常のテキスト回答
    current_qid = user.get("current_question_id")
    if current_qid:
        save_master_user_response(user_id, account["id"], current_qid, response=text)
        next_qid = get_master_next_question_id_by_conditions(current_qid, user_id)
        
        if next_qid == "006b7220-ab96-4d81-a549-55c611846f85":
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
                

        # 今の質問が最後の質問かどうか判定
        if current_qid == "7da777b9-6100-4ea7-bdbd-9d06d9bf9d83":
            send_final_email(user_id, account)
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

async def master_handle_postback(event, account, api, reply_token):
    from urllib.parse import unquote

    line_id = event.source.user_id
    data = dict(pair.split("=", 1) for pair in event.postback.data.split("&"))
    option_id = data.get("option_id")
    question_id = data.get("question_id")
    response = unquote(data.get("response", ""))
    
    profile = api.get_profile(line_id)
    display_name = profile.display_name
    
    user = get_or_create_line_user(line_id, account["id"], display_name)
    
    user_id = user["id"]

    save_master_user_response(user_id, account["id"], question_id, option_id, response)
    upsert_line_user(user_id, question_id)

    if question_id == "7da777b9-6100-4ea7-bdbd-9d06d9bf9d83":
        send_final_email(user_id, account)
        supabase.table("line_users").update({"is_answer_complete": True}).eq("id", user_id).execute()

    next_qid = get_master_next_question_id_by_conditions(question_id, user_id)
    
    if next_qid == "006b7220-ab96-4d81-a549-55c611846f85":
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


async def handle_text(event, account, api):
    user_id = event.source.user_id
    text = event.message.text
    reply_token = event.reply_token
    
    if event.message.text == "計算結果":
        handle_calculation_request(user_id, account, api, reply_token)
        return

    # トリガー対応（例：キーワードで質問開始）
    start_res = supabase.table("start_triggers").select("question_id").eq("account_id", account["id"]).eq("keyword", text).execute()
    if start_res.data:
        question_id = start_res.data[0]["question_id"]
        question = get_question(account["id"], question_id)
        options = get_options(question_id)
        upsert_line_user(user_id, account["id"], question_id)

        if options:
            send_question_with_image_options(api, reply_token, question, options)
        else:
            api.reply_message(reply_token, TextSendMessage(text=question["text"]))
        return

    # 通常のテキスト回答
    user = get_or_create_line_user(user_id, account["id"])
    current_qid = user.get("current_question_id")
    if current_qid:
        save_user_response(user_id, account["id"], current_qid, response=text)
        next_qid = get_next_question_id_by_conditions(account["id"], current_qid, user_id)

        # 今の質問が最後の質問かどうか判定
        if current_qid == account.get("final_question_id"):
            send_final_email(user_id, account)
            api.reply_message(reply_token, TextSendMessage(text="ご回答ありがとうございました。")) 


        next_q = get_question(account["id"], next_qid)
        options = get_options(next_qid)
        upsert_line_user(user_id, account["id"], next_qid)
        if options:
            send_question_with_image_options(api, reply_token, next_q, options)
        else:
            api.reply_message(reply_token, TextSendMessage(text=next_q["text"]))

async def handle_postback(event, account, api, reply_token):
    from urllib.parse import unquote

    user_id = event.source.user_id
    data = dict(pair.split("=", 1) for pair in event.postback.data.split("&"))
    option_id = data.get("option_id")
    question_id = data.get("question_id")
    response = unquote(data.get("response", ""))

    save_user_response(user_id, account["id"], question_id, option_id, response)
    upsert_line_user(user_id, account["id"], question_id)

    if question_id == account.get("final_question_id"):
        send_final_email(user_id, account)
        api.reply_message(reply_token, TextSendMessage(text="ご回答ありがとうございました。"))
        return

    next_qid = get_next_question_id_by_conditions(account["id"], question_id, user_id)
    if not next_qid:
        send_final_email(user_id, account)
        api.reply_message(reply_token, TextSendMessage(text="ご回答ありがとうございました。"))
        return

    next_q = get_question(account["id"], next_qid)
    options = get_options(next_qid)
    upsert_line_user(user_id, account["id"], next_qid)
    if options:
        send_question_with_image_options(api, reply_token, next_q, options)
    else:
        api.reply_message(reply_token, TextSendMessage(text=next_q["text"]))

def send_question_with_image_options(api, reply_token, question, options):
    messages = [TextSendMessage(text=question["text"])]
    columns = [
        ImageCarouselColumn(
            image_url=opt["image_url"],
            action=PostbackAction(
                label=opt["text"],
                display_text=opt["text"],
                data=f"option_id={opt['id']}&question_id={question['id']}&response={quote(opt['text'])}"
            )
        ) for opt in options if opt.get("image_url")
    ]
    if columns:
        messages.append(
            TemplateSendMessage(
                alt_text=question["title"],
                template=ImageCarouselTemplate(columns=columns)
            )
        )
    api.reply_message(reply_token, messages)

def send_master_question_with_image_options(api, reply_token, question, options, account_id):
    placeholders = extract_placeholders(question["text"])
    data = fetch_data_for_template(placeholders, account_id)
    rendered = render_template(question["text"], data)
    messages = [TextSendMessage(text=rendered)]
    columns = []
    text_options = []

    for opt in options:
        res = supabase.table("option_images").select("images (url)").eq("master_option_id", opt["id"]).eq("account_id", account_id).execute()
        
        image_url = res.data[0]["images"]["url"] if res.data else None
        print(image_url)

        if image_url:
            columns.append(
                ImageCarouselColumn(
                    image_url=image_url,
                    action=PostbackAction(
                        label=opt["text"],
                        display_text=opt["text"],
                        data=f"option_id={opt['id']}&question_id={question['id']}&response={quote(opt['text'])}"
                    )
                )
            )
        else:
            text_options.append(
                PostbackAction(
                    label=opt["text"],
                    display_text=opt["text"],
                    data=f"option_id={opt['id']}&question_id={question['id']}&response={quote(opt['text'])}"
                )
            )

    if columns:
        messages.append(
            TemplateSendMessage(
                alt_text=question["title"],
                template=ImageCarouselTemplate(columns=columns)
            )
        )
    elif text_options:
        messages.append(
            TemplateSendMessage(
                alt_text=question["title"],
                template=ButtonsTemplate(
                    text=question["text"],
                    actions=text_options
                )
            )
        )
    api.reply_message(reply_token, messages)
    

def send_final_email(user_id: str, account: dict):
    template = get_master_email_template("6a3ec14f-79d0-4762-a8a6-107a8e22e6ce")
    # to_email = get_user_answer_response(user_id, account["id"], account["email_answer_question_id"])
    to_email = account["email"]
    if not to_email:
        return

    subject = render_master_template_with_answers(template["subject"], user_id)
    body = render_master_template_with_answers(template["body"], user_id)
    send_email_via_mailtrap(to_email, subject, body)
    
def extract_placeholders(template: str) -> set:
    """{table.column} のプレースホルダを全て抽出"""
    return set(re.findall(r"{([\w]+\.[\w]+)}", template))

def render_template(template: str, values: dict) -> str:
    """値を埋め込んでテンプレートをレンダリング"""
    def replacer(match):
        table_col = match.group(1)
        table, col = table_col.split(".")
        return str(values.get(table, {}).get(col, f"{{{table_col}}}"))  # 未知ならそのまま残す

    return re.sub(r"{([\w]+\.[\w]+)}", replacer, template)

def fetch_data_for_template(placeholders: set, account_id: str) -> dict:
    """テンプレートに必要なテーブルをSupabaseから取得"""
    table_columns = defaultdict(set)

    # テーブルごとに使われているカラム名を集める
    for ph in placeholders:
        table, column = ph.split(".")
        table_columns[table].add(column)

    results = {}

    for table, columns in table_columns.items():
        # account_id を持つテーブルだけに限定（必要に応じて他条件も）
        if table == "accounts":
            response = supabase.table(table).select("*").eq("id", account_id).maybe_single().execute()
        else:
            response = supabase.table(table).select("*").eq("account_id", account_id).maybe_single().execute()

        if response.data:
            results[table] = response.data
        else:
            results[table] = {}

    return results

def generate_result_message(responses):
    
    question_id_dict = {
        'disablity_id': 'b796ac9c-31a7-4af4-9ab8-180976b32c20',
        'gender_id': '46171ff3-212d-4771-9757-4a5e0e50d50b', 
        'income_id': 'c3856e91-d602-48ce-a398-18ecff70d1ef', 
        'marital_status_id': '2d98f15a-a964-46c5-8dba-4a18e0d6a7bc',
        'victim_id': 'a0d898ab-1a9f-4dc1-8bf7-82667181c548',
        'accident_id': '7c0294cb-a6ab-4e38-afd4-3e0039d2f8ab',
        'injury_id': 'c9edae43-b444-4ff1-8eac-9b9c6eaa926b',
        'treatment_status_id': '614ff372-98b9-4de2-9b1f-0fd000dc758d',
        'has_income_id': '99fc3515-70bb-4699-9658-e8ca12c0ffce',
        'hospitalization_id': '62f108be-a166-4ead-81d9-e59957fb99e1',
        'outpatient_id': '98d4ceca-c229-476e-9454-d95bb1d24d65',
        'actual_outpatient_id': 'e0bc0d91-1587-40df-97c2-a955a96bf6c8',
        'day_off_id': '48eefe11-6f5e-4a87-964a-d4683dbb2d53',
        'age_id': 'f0a157e8-b9ea-44f0-ab6e-25554bdeff40',
        'role_id': '1cab33c2-0cce-4f6d-92ef-6b46b9f58537',
        'dependents_id': '7b1ac05b-1e88-4b43-8ca6-2f35734ae332',
    }
    
    type = responses.get(question_id_dict.get('accident_id'))
    
    text = ""
    
    if type == "死亡":
        death_compensation = calculate_death_compensation(responses.get(question_id_dict.get('role_id')))
        relatives = int(responses.get(question_id_dict.get('dependents_id')))
        if responses.get(question_id_dict.get('marital_status_id')) == "既婚":
            relatives += 1
        
        auto_death_compensation = calculate_auto_death_compensation(int(responses.get(question_id_dict.get('dependents_id'))), relatives)
        
        death_lost_profits = calculate_death_lost_profits(
            int(responses.get(question_id_dict.get('income_id'))) * 10000,
            responses.get(question_id_dict.get('role_id')),
            responses.get(question_id_dict.get('gender_id')),
            int(responses.get(question_id_dict.get('dependents_id'))),
            int(responses.get(question_id_dict.get('age_id'))),
        )
        
        auto_death_lost_profits = death_lost_profits
        
        if auto_death_compensation + auto_death_lost_profits > 30000000:
            auto_death_lost_profits = 30000000 - auto_death_compensation
        
        
        total = death_compensation + death_lost_profits
        auto_total = auto_death_compensation + auto_death_lost_profits
        
        text = (f"診断結果\n\n"
            f"✓死亡慰謝料\n"
            f"（弁護士基準）: {death_compensation // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_death_compensation // 10000:,} 万円\n"
            f"✓逸失利益\n"
            f"（弁護士基準）: {death_lost_profits // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_death_lost_profits // 10000:,} 万円\n"
            f"✓総額\n"
            f"（弁護士基準）: {total // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_total // 10000:,} 万円\n\n"
            f"自賠責基準の場合、慰謝料{auto_total // 10000:,}万円のところ、弁護士に依頼することで{(total - auto_total) // 10000 :,}万円増額の総額{total // 10000 :,}万円受け取ることができる可能性があります。\n"
            f"※こちらの結果はあくまで目安となります。詳しくは弁護士にご相談ください。"
        )
        
    else:
        injury_compensation = calculate_injury_compensation(int(responses.get(question_id_dict.get('hospitalization_id'))) // 30, int(responses.get(question_id_dict.get('actual_outpatient_id'))) // 30, type)
        auto_injury_compensation = calculate_auto_injury_compensation(int(responses.get(question_id_dict.get('outpatient_id'))), int(responses.get(question_id_dict.get('actual_outpatient_id'))))
        
        lost_income = calculate_lost_income(int(responses.get(question_id_dict.get('income_id'))) * 10000, int(responses.get(question_id_dict.get('day_off_id'))))
        auto_lost_income = calculate_auto_lost_income(int(responses.get(question_id_dict.get('day_off_id'))))
        
        disability_compensation_data = calculate_disability_compensation(int(responses.get(question_id_dict.get('disablity_id'))))
        disability_compensation = disability_compensation_data["amount_lawyer"]
        auto_disability_compensation = disability_compensation_data["amount_auto"]
        
        lost_profits = calculate_lost_profits(int(responses.get(question_id_dict.get('income_id'))) * 10000, int(responses.get(question_id_dict.get('age_id'))), int(responses.get(question_id_dict.get('disablity_id'))), type)
        
        auto_disability_limit = supabase.table("auto_limit_amounts").select("amount").eq("grade", int(responses.get(question_id_dict.get('disablity_id')))).single().execute()
        auto_lost_profits = lost_profits
        
        if auto_disability_compensation + auto_lost_profits > auto_disability_limit.data["amount"]:
            auto_lost_profits = auto_disability_limit.data["amount"] - auto_disability_compensation
        
        total = injury_compensation + lost_income + disability_compensation + lost_profits
        auto_total = auto_injury_compensation + auto_lost_income + auto_disability_compensation + auto_lost_profits
        
        text = (f"診断結果\n\n"
            f"✓入通院慰謝料\n"
            f"（弁護士基準）: {injury_compensation // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_injury_compensation // 10000:,} 万円\n"
            f"✓休業損害\n"
            f"（弁護士基準）: {lost_income // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_lost_income // 10000:,} 万円\n"
            f"✓後遺障害慰謝料\n"
            f"（弁護士基準）: {disability_compensation // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_disability_compensation // 10000:,} 万円\n"
            f"✓逸失利益\n"
            f"（弁護士基準）: {lost_profits // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_lost_profits // 10000:,} 万円\n"
            f"✓総額\n"
            f"（弁護士基準）: {total // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_total // 10000:,} 万円\n\n"
            f"自賠責基準の場合、慰謝料{auto_total // 10000:,}万円のところ、弁護士に依頼することで{(total - auto_total) // 10000 :,}万円増額の総額{total // 10000 :,}万円受け取ることができる可能性があります。\n"
            f"※こちらの結果はあくまで目安となります。詳しくは弁護士にご相談ください。"
        )
    
    return text