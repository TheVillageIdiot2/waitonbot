import SheetUtil #For read from waiton sheet
from tabulate import tabulate
from SlackUtil import reply
"""
This file contains util for waiton polling.
Only really kept separate for neatness sake.
"""

#ID of waiton sheet on drive
WAITON_SHEET_ID = "1J3WDe-OI7YjtDv6mMlM1PN3UlfZo8_y9GBVNBEPwOhE"



"""
Pulls waiton data from the spreadsheet.
Returns waitons as list of objects, each of form
{
    name: <brothername>,
    date: <date as string>,
    meal: <meal as string>
}
"""
def getWaitons(sheet_service):
    #Propogate dates to each row
    def fixDates(values):
        curr_date = None
        curr_dow = None
        last_row = None
        for row in values:
            date_col = row[0]
            
            #Update date if it is more or less a date
            if "/" in date_col:
                curr_date = date_col

            #Update previous row
            if curr_date is not None:
                last_row[0] = curr_dow + " - " + curr_date
            
            #Update DOW now that previous row will not be affected "" != date_col:
            if "/" not in date_col and "" != date_col:
                curr_dow = date_col
            
            #Cycle last_row
            last_row = row
            
        #Fix the last row
        if last_row is not None:
            last_row[0] = curr_dow + " - " + curr_date
                
    #Propogate meal data to each row
    def fixMeals(values):
        curr_meal = None
        for row in values:
            #Update curr meal:
            if row[1] != "":
                curr_meal = row[1]
            
            if curr_meal is not None:
                row[1] = curr_meal
                
    #Helper to remove steward rows
    def filterStewards(values):
        return [row for row in values if len(row) > 2]
        
    #Helper to remove empty rows (IE no assignees)
    def filterUnset(values):
        return [row for row in values if "---" not in row[2]]
        
    pageContents = SheetUtil.getAllPageValues(sheet_service, WAITON_SHEET_ID)

    #Filter junk rows
    pageContents = [filterStewards(x) for x in pageContents]
    pageContents = [filterUnset(x) for x in pageContents]
    
    #Fix stuff (make each have full info)
    for pc in pageContents:
        fixDates(pc)
        fixMeals(pc)
    
    #Merge, using property of python list concatenation via add (+)
    allWaitons = sum(pageContents, [])
    
    #Parse to objects
    waitonObjects = [{
        "name": row[2],
        "date": row[0],
        "meal": row[1]        
        } for row in allWaitons]
    
    return waitonObjects
    


"""
Takes a slack context, a message to reply to, and a user to look up waitons for.
Additionally, takes a for_user flag for message formatting
IE "user" asked for "for_user" waitons, so blah blah blah
"""
def handleWaitonMsg(slack, sheet_service, msg, user, for_user=None):
    """
    Filters to waitons with the given name 
    """
    def filterWaitons(waitons, first, last):
        def valid(waiton):
            return first in waiton["name"] or last in waiton["name"]
            
        return [w for w in waitons if valid(w)]
    
    """
    Formats waitons for output
    """
    def formatWaitons(waitons):
        waitonRows = [(w["name"], w["date"], w["meal"]) for w in waitons]
        return tabulate(waitonRows)
    
    #Create format string
    response = ( "{0} asked for waiton information{1}, so here are his waitons:\n"
                "{2}")
        
    #Get names of caller
    requestor_first = user['user']['profile']['first_name']
    requestor_last  = user['user']['profile']['last_name']
    
    #Get names of target user
    for_first = (for_user or user)['user']['profile']['first_name']
    for_last  = (for_user or user)['user']['profile']['last_name']
    
    #Get waitons for target user
    waitons = getWaitons(sheet_service)
    waiton_string = formatWaitons( filterWaitons(waitons, for_first, for_last))
    
    f_response = response.format(requestor_first, " for {0}".format(for_first) if for_user else "", waiton_string)
    
    reply(slack, msg, f_response, username="mealbot")
 
