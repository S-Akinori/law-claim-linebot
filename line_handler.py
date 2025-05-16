# line_handler.py
from fastapi import APIRouter, Request, Query
from linebot import LineBotApi, WebhookParser
from linebot.models import *
from dotenv import load_dotenv
from utils import (
    get_account_info,
)

from master.master_handle_text import master_handle_text
from master.master_handle_postback import master_handle_postback
from account.handle_text import handle_text
from account.handle_post_back import handle_postback


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
    use_master = account['use_master']
    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
            if use_master:
                await master_handle_text(event, account, line_bot_api)
            else:
                await handle_text(event, account, line_bot_api)
        elif isinstance(event, PostbackEvent):
            if use_master:
                await master_handle_postback(event, account, line_bot_api, event.reply_token)
            else:
                await handle_postback(event, account, line_bot_api, event.reply_token)

    return "OK"
