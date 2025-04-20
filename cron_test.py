import requests

response = requests.get("https://8319-153-195-55-158.ngrok-free.app/scheduled-messages/send")

if response.status_code == 200:
    print("✅ 成功:", response.json())  # {'message': 'こんにちは、FastAPI!'}
else:
    print("❌ エラー:", response.status_code, response.text)