import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

def authenticate_sheets(credential_file="service_account.json"):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(credential_file, scope)
    client = gspread.authorize(creds)
    return client

def write_to_sheet(data, sheet_id, worksheet_name, headers):
    """
    Writes a list of dictionaries to a specific worksheet.
    data: List[Dict]
    """
    client = authenticate_sheets()
    sh = client.open_by_key(sheet_id)
    
    try:
        worksheet = sh.worksheet(worksheet_name)
        worksheet.clear()
    except gspread.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=worksheet_name, rows=100, cols=20)
        
    if not data:
        return
        
    # Prepare rows
    rows = [headers]
    for item in data:
        row = []
        for h in headers:
            # Map header to data key. 
            # If header is 'Description_EN', look for 'Description_EN' then 'Description'
            key = h
            val = item.get(key)
            if val is None and key.endswith("_EN"):
                val = item.get(key[:-3]) # Try without _EN
            
            if val is None:
                val = ""

            # Auto-format images for Google Sheets
            if h == "Icon" and val and val.startswith("http"):
                val = f'=IMAGE("{val}")'
            row.append(val)
        rows.append(row)
        
    worksheet.update("A1", rows, value_input_option="USER_ENTERED")

def export_all_data(sheet_id, heroes, skills, engraving, signature, furniture):
    # --- Heroes ---
    hero_cols = ["Icon","Name","Faction","Type","Class","Rarity","Role",
                 "Primary Role","Secondary Role",
                 "Overall_EN", "Overall_VN",
                 "Personality_EN", "Personality_VN",
                 "Background_EN", "Background_VN",
                 "Quotes_EN", "Quotes_VN",
                 "Trivia_EN", "Trivia_VN",
                 "URL"]
    write_to_sheet(heroes, sheet_id, "Heroes", hero_cols)
    
    # --- Skills ---
    skill_cols = ["Hero","Icon","Unlock Level", 
                  "Skill Name", 
                  "Type", 
                  "Description_EN", "Description_VN"]
    write_to_sheet(skills, sheet_id, "Skills", skill_cols)
    
    # --- Engraving ---
    engr_cols = ["Hero","Icon",
                 "Skill Name", 
                 "Unlock Level", 
                 "Description_EN", "Description_VN"]
    write_to_sheet(engraving, sheet_id, "Engraving Abilities", engr_cols)
    
    # --- Signature ---
    sig_cols = ["Hero", "Description_EN", "Description_VN"]
    write_to_sheet(signature, sheet_id, "Signature Item", sig_cols)
    
    # --- Furniture ---
    furn_cols = ["Hero","Icon",
                 "Name", 
                 "Description_EN", "Description_VN"]
    write_to_sheet(furniture, sheet_id, "Furniture Set Bonuses", furn_cols)
