import os
import json
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
import uvicorn
import redis

try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ImportError:
    raise RuntimeError("Please install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("xoyo.google_agent")

app = FastAPI(title="XOYO Google Agent")

# Setup Redis for token storage
try:
    rc = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    rc.ping()
except Exception as e:
    log.error(f"Redis not available: {e}")
    rc = None

# OAuth 2.0 configuration
# Expected in the environment or .env file
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.readonly'
]

# We construct a client config dynamically to avoid needing a json file
CLIENT_CONFIG = {
    "web": {
        "client_id": CLIENT_ID,
        "project_id": "xoyo-google-agent",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["http://localhost:8050/auth/callback"]
    }
}

def get_credentials():
    if not rc:
        return None
    token_json = rc.get("xoyo:google_token")
    if not token_json:
        return None
    token_data = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    return creds

@app.get("/auth/login")
def login():
    if not CLIENT_ID or not CLIENT_SECRET:
        return {"error": "Google Client ID and Secret not configured."}
    
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri="http://localhost:8050/auth/callback"
    )
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def callback(code: str):
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri="http://localhost:8050/auth/callback"
    )
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        return {"error": f"Failed to fetch token: {e}"}
    creds = flow.credentials
    
    if rc:
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes
        }
        rc.set("xoyo:google_token", json.dumps(token_data))
    
    return {"status": "success", "message": "Google Account successfully linked to XOYO."}

@app.get("/auth/status")
def status():
    creds = get_credentials()
    if creds and creds.valid:
        return {"status": "authenticated"}
    elif creds and creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request as GRequest
            creds.refresh(GRequest())
            if rc:
                token_data = {
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": creds.scopes
                }
                rc.set("xoyo:google_token", json.dumps(token_data))
            return {"status": "authenticated", "note": "token_refreshed"}
        except Exception:
            return {"status": "unauthenticated"}
    return {"status": "unauthenticated"}

# ── API ENDPOINTS ──────────────────────────────────────────

@app.post("/gmail/read")
def read_emails(query: str = "is:unread", max_results: int = 5):
    creds = get_credentials()
    if not creds: return {"error": "Not authenticated with Google"}
    
    service = build('gmail', 'v1', credentials=creds)
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        out = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
            headers = msg_data.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
            sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown")
            out.append({"id": msg['id'], "snippet": msg_data.get('snippet'), "subject": subject, "from": sender})
        
        return {"emails": out}
    except Exception as e:
        return {"error": f"Gmail API error: {e}"}

@app.post("/calendar/list")
def list_events(max_results: int = 10):
    creds = get_credentials()
    if not creds: return {"error": "Not authenticated with Google"}
    
    import datetime
    service = build('calendar', 'v3', credentials=creds)
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    try:
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=max_results, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        out = []
        for e in events:
            start = e['start'].get('dateTime', e['start'].get('date'))
            out.append({"summary": e.get('summary'), "start": start, "link": e.get('htmlLink')})
        return {"events": out}
    except Exception as e:
        return {"error": f"Calendar API error: {e}"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "google_agent"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8050)
