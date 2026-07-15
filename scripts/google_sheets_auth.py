"""
One-time Google Sheets OAuth2 authorization.
Run in terminal: python scripts/google_sheets_auth.py
Token/client JSONs live at the project root (BASE_DIR) — the app reads them there.
"""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES     = ['https://www.googleapis.com/auth/spreadsheets.readonly',
              'https://www.googleapis.com/auth/drive.readonly']
BASE_DIR   = Path(__file__).resolve().parent.parent
TOKEN_FILE = BASE_DIR / 'google_sheets_token.json'
CLIENT_FILE = BASE_DIR / 'google_sheets_client.json'

flow  = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
creds = flow.run_local_server(port=0)

TOKEN_FILE.write_text(creds.to_json())
print(f'\nSuccess! Token saved to: {TOKEN_FILE}')
print('The server can now access any Google Sheet shared with ezzydelivery@gmail.com.')
