"""
Examples provided by google for using their api.
Very slightly modified by me to easily just get credentials
"""

from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/sheets.googleapis.com-python-quickstart.json
SCOPES = 'https://www.googleapis.com/auth/spreadsheets'
APPLICATION_NAME = 'SlickSlacker'


def _init_sheets_service():
    store = file.Storage('sheets_token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('sheets_credentials.json', SCOPES)
        creds = tools.run_flow(flow, store)
    service = build('sheets', 'v4', http=creds.authorize(Http()))
    return service


_global_sheet_service = _init_sheets_service()


# range should be of format 'SHEET NAME!A1:Z9'
def get_sheet_range(spreadsheet_id, sheet_range):
    """
    Gets an array of the desired table
    """
    result = _global_sheet_service.spreadsheets().values().get(spreadsheetId=spreadsheet_id,
                                                               range=sheet_range).execute()
    values = result.get('values', [])
    if not values:
        return []
    else:
        return values


def set_sheet_range(spreadsheet_id, sheet_range, values):
    """
    Set an array in the desired table
    """
    body = {
        "values": values
    }
    result = _global_sheet_service.spreadsheets().values().update(spreadsheetId=spreadsheet_id,
                                                                  range=sheet_range,
                                                                  valueInputOption="RAW",
                                                                  body=body).execute()
    return result


def get_calendar_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir, 'calendar-python-quickstart.json')

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else:  # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials
    """
    raise NotImplementedError("This isn't going to work")
