import requests

response = requests.get("https://5b1d-240b-10-2aa0-1700-952a-2e43-3105-d6b2.ngrok-free.app/scheduled-messages/send")

if response.status_code == 200:
    print("✅ 成功:", response.json())  # {'message': 'こんにちは、FastAPI!'}
else:
    print("❌ エラー:", response.status_code, response.text)