import requests

response = requests.get("https://ba4f-2400-4070-3b23-8d10-389e-dc87-379a-2dcf.ngrok-free.app/not-complete-messages/send")

if response.status_code == 200:
    print("✅ 成功:", response.json())  # {'message': 'こんにちは、FastAPI!'}
else:
    print("❌ エラー:", response.status_code, response.text)