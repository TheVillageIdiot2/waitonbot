"""
This file contains general utility for polling google sheets.
Note that it is not used for the REQUISITION of the service,
as that is in the domain of GoogleApi.py.

It is instead for more general things, like parsing a sheet into 2d array,
etc.
My goal is to abstract all of the sheets bullshit out, and make reading
from a sheet as easy as working with a 2d array, as well as making it
fairly fast.
"""

"""
Gets a spreadsheet object from a sheet id
"""
def getSpreadsheet(sheet_service, sheet_id):
    #Get the spreadsheet
    spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=sheet_id).execute()

    #And let him have it!
    return spreadsheet 



"""
Gets the names of every page in a spreadsheet.
"""
def getPageNames(spreadsheet):
    pageNames = [sheet["properties"]["title"] for sheet in spreadsheet["sheets"]]
    return pageNames



"""
Gets the contents of a page in its entirety, as a 2d array.
TODO: Make this take a spreadsheet object.
Unfortunately, the spreadsheet object doc is literally 20k lines long of 
poorly formatted text(seriously, what the fuck)
"""
def getPageContents(sheet_service, sheet_id, pageName, range="$A1$1:$YY"):
    sheet_range = pageName + "!" + range
    values = sheet_service.spreadsheets().values()
    result = values.get(spreadsheetId=sheet_id, range=sheet_range).execute()

    return result.get('values', [])
    

"""
Gets all pages as 2d arrays. from spreadsheet.
Pages are appended, in order.
So basically, you get an array of 2d arrays representing spreadsheet pages
"""
def getAllPageValues(sheet_service, sheet_id):
    #Get all page names
    pageNames = getPageNames(getSpreadsheet(sheet_service, sheet_id))

    #Get values for each page 
    pageContents = [getPageContents(sheet_service, sheet_id, name, range="A2:D") for name in pageNames]

    return pageContents
        
