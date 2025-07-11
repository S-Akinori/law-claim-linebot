from fastapi import APIRouter
from datetime import datetime
from db import supabase
from dateutil.parser import parse
import logging
from postgrest.exceptions import APIError

# ログ設定
logging.basicConfig(level=logging.INFO)

router = APIRouter()

import os
from dotenv import load_dotenv

load_dotenv()

env = os.getenv("ENV")

@router.get("/scheduled-messages/send")
async def send_scheduled_messages():
    now = datetime.now()
    current_hour = now.hour
    current_minute = now.minute
    
    # 15分バッファ → 許容されるhour候補: H-1, H, H+1
    hour_candidates = set()
    if current_minute < 15:
        hour_candidates.update({(current_hour - 1) % 24, current_hour})
    elif current_minute >= 45:
        hour_candidates.update({current_hour, (current_hour + 1) % 24})
    else:
        hour_candidates.add(current_hour)
        

    # アカウントごとに処理
    accounts_res = supabase.table("accounts").select("id").execute()
    accounts = accounts_res.data if accounts_res.data else []
    
    if(env == "development"):
        account_id = "6ad4edfa-13e7-4357-a2cc-7e1da2168d80"
        users_res = supabase.table("line_users").select("*").eq("account_id", account_id).eq("is_answer_complete", False).execute()
        msg_res = supabase.table("master_scheduled_messages").select("id, message").execute()
        data = msg_res.data if msg_res.data else []
        if data:
            import random
            random_message = random.choice(data)
            
            for user in users_res.data:
                user_id = user["id"]
                line_user_id = user["line_id"]
                placeholders = extract_placeholders(random_message["message"])
                data = fetch_data_for_template(placeholders, account_id, user_id)
                rendered = render_template(random_message["message"], data)
                # メッセージ送信
                send_line_message(line_user_id, rendered, account_id=account_id)
            
            return { "message": f"Sent message: {rendered}" }
        else:
            return { "message": "No messages found." }
        
    
    for account in accounts:
        account_id = account["id"]
        
        # 対象ユーザー取得（回答未完了のみ）
        users_res = supabase.table("line_users").select("*").eq("account_id", account_id).eq("is_answer_complete", False).execute()

        if not users_res.data:
            continue

        for user in users_res.data:
            user_id = user["id"]
            line_user_id = user["line_id"]
            
            
            registered_at = parse(user["created_at"])
            day_offset = (now.date() - registered_at.date()).days
            
            # hour候補ごとにチェック
            for hour in hour_candidates:
                msg_res = supabase.table("master_scheduled_messages").select("id, message").eq("day_offset", day_offset).eq("hour", hour).execute()
                
                if not msg_res.data:
                    continue
            
                # 送信済みチェック
                sent_res = supabase.table("scheduled_message_logs").select("scheduled_message_id").eq("line_user_id", user_id).execute()

                sent_ids = {row["scheduled_message_id"] for row in sent_res.data} if sent_res.data else set()

                for msg in msg_res.data:
                    if msg["id"] in sent_ids:
                        continue
                    
                    placeholders = extract_placeholders(msg["message"])
                    data = fetch_data_for_template(placeholders, account_id, user_id)
                    rendered = render_template(msg["message"], data)

                    # メッセージ送信
                    send_line_message(line_user_id, rendered, account_id=account_id)

                    # ログ記録
                    supabase.table("scheduled_message_logs").insert({
                        "line_user_id": user_id,
                        "account_id": account_id,
                        "scheduled_message_id": msg["id"],
                        "success": True
                    }).execute()

    return {"status": "done"}

import requests

LINE_API_URL = "https://api.line.me/v2/bot/message/push"

def send_line_message(line_user_id: str, message: str, account_id: str):
    # アカウントに紐づくLINEチャネル情報を取得
    account_res = supabase.table("accounts").select("line_channel_access_token").eq("id", account_id).maybe_single().execute()

    if not account_res.data:
        print(f"[ERROR] LINE access token not found for account: {account_id}")
        return

    access_token = account_res.data["line_channel_access_token"]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "to": line_user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    try:
        response = requests.post(LINE_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        print(f"[SUCCESS] Sent message to {line_user_id}")
    except requests.RequestException as e:
        print(f"[ERROR] Failed to send message to {line_user_id}: {e}")

import re
from collections import defaultdict

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

def fetch_data_for_template(placeholders: set, account_id: str, user_id: str = None) -> dict:
    """テンプレートに必要なテーブルをSupabaseから取得"""
    table_columns = defaultdict(set)

    # テーブルごとに使われているカラム名を集める
    for ph in placeholders:
        table, column = ph.split(".")
        table_columns[table].add(column)

    results = {}

    for table, columns in table_columns.items():
        try:
            logging.info(f"Fetching data for table: {table}, columns: {columns}")
            if table == "accounts":
                response = supabase.table(table).select("*").eq("id", account_id).maybe_single().execute()
            elif table == "line_users" and user_id:
                response = supabase.table(table).select("*").eq("id", user_id).maybe_single().execute()
            else:
                response = supabase.table(table).select("*").eq("account_id", account_id).maybe_single().execute()

            if response.data:
                results[table] = response.data
            else:
                results[table] = {}
        except APIError as e:
            if e.code == '204':  # No content
                results[table] = {}
            else:
                raise e

    return results
