import base64
import requests
from django.shortcuts import render
from django.conf import settings

def fetch_transactions():
    api_key = settings.XENDIT_SECRET_API_KEY
    
    # Base64 encode for Basic Auth
    encoded_key = base64.b64encode(f"{api_key}:".encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded_key}"
    }

    url = "https://api.xendit.co/transactions"
    params = {
        "currency": "PHP",  # Set this to the appropriate currency
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        return data.get("data", [])
    else:
        print("Xendit API error:", response.status_code, response.text)
        return []
        
def dashboard_view(request):
    try:
        transactions = fetch_transactions()
        print(transactions)

    except Exception as e:
        print("Error fetching transactions:", e)
        transactions = []

    return render(request, 'dashboard/dashboard.html', {'transactions': transactions})
