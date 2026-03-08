"""
One-time Google Sheets OAuth2 authorization.
Run in terminal: python google_sheets_auth.py
"""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES     = ['https://www.googleapis.com/auth/spreadsheets.readonly',
              'https://www.googleapis.com/auth/drive.readonly']
TOKEN_FILE = Path(__file__).parent / 'google_sheets_token.json'
CLIENT_FILE = Path(__file__).parent / 'google_sheets_client.json'

flow  = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
creds = flow.run_local_server(port=0)

TOKEN_FILE.write_text(creds.to_json())
print(f'\nSuccess! Token saved to: {TOKEN_FILE}')
print('The server can now access any Google Sheet shared with ezzydelivery@gmail.com.')
