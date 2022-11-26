import pyperclip
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/calendar']
flow = InstalledAppFlow.from_client_secrets_file('creds.json', SCOPES)
creds = flow.run_local_server(port=0)
# Save the credentials for the next run
with open('token.json', 'w') as token:
    token.write(creds.to_json())
    pyperclip.copy(str(creds.to_json()))