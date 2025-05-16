import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 認証スコープとクレデンシャル読み込み
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
