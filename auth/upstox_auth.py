import os
import webbrowser
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import requests
from dotenv import load_dotenv, set_key

load_dotenv()

app = FastAPI()

API_KEY      = os.getenv("UPSTOX_API_KEY")
API_SECRET   = os.getenv("UPSTOX_API_SECRET")
REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI")


@app.get("/callback", response_class=HTMLResponse)
async def callback(code: str):
    response = requests.post(
        "https://api.upstox.com/v2/login/authorization/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "code":          code,
            "client_id":     API_KEY,
            "client_secret": API_SECRET,
            "redirect_uri":  REDIRECT_URI,
            "grant_type":    "authorization_code",
        }
    )

    data = response.json()
    access_token = data.get("access_token")

    if access_token:
        set_key(".env", "UPSTOX_ACCESS_TOKEN", access_token)
        return """
            <h2 style='font-family:sans-serif;color:green'>Login successful!</h2>
            <p style='font-family:sans-serif'>Access token saved. You can close this tab and return to your terminal.</p>
        """
    else:
        return f"""
            <h2 style='font-family:sans-serif;color:red'>Login failed</h2>
            <pre>{data}</pre>
        """


def login():
    url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code"
        f"&client_id={API_KEY}"
        f"&redirect_uri={REDIRECT_URI}"
    )
    print(f"Opening browser for Upstox login...")
    webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=5000, log_level="warning")


if __name__ == "__main__":
    login()