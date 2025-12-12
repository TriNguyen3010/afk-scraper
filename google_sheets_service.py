import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

def authenticate_sheets(credential_file="service_account.json"):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(credential_file, scope)
    client = gspread.authorize(creds)
    return client

def get_existing_data(worksheet):
    try:
        return worksheet.get_all_records()
    except gspread.exceptions.GSpreadException:
        return []

def get_dynamic_headers(data, priority_fields=None):
    if not data:
        return priority_fields or []
        
    all_keys = set()
    for item in data:
        all_keys.update(item.keys())
        
    # Start with priority fields that exist in data (or forced ones)
    headers = []
    if priority_fields:
        for f in priority_fields:
            if f in all_keys:
                headers.append(f)
                all_keys.remove(f)
            # Optional: if you want to force a column even if empty, handle here.
            # But let's only show what we have + standard ID columns
            elif f in ["ID", "Name", "Hero", "Icon"]: # Always include core identity cols
                headers.append(f)

    # Append rest, but explicitly EXCLUDE "Hero ID"
    remaining = sorted(list(all_keys))
    for k in remaining:
        if k != "Hero ID":
             headers.append(k)
             
    return headers

def update_heroes_sheet(sh, heroes):
    # Dynamic headers for Heroes (User specified order)
    priority = ["ID", "Icon","Name","Faction","Type","Class","Rarity","Role",
                "Primary Role","Secondary Role", 
                "Overall_EN", "Overall_VN", 
                "Personality_EN", "Personality_VN", 
                "Background_EN", "Background_VN", 
                "Quotes_EN", "Quotes_VN", 
                "Trivia_EN", "Trivia_VN", 
                "URL"]
    
    # Check keys from input data
    headers = get_dynamic_headers(heroes, priority)
    
    try:
        ws = sh.worksheet("Heroes")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Heroes", rows=100, cols=20)
        ws.append_row(headers)
        
    existing = get_existing_data(ws)
    
    # Sync headers
    current_headers = ws.row_values(1)
    if not current_headers:
        current_headers = headers
        ws.append_row(headers)
        
    new_cols = [h for h in headers if h not in current_headers]
    if new_cols:
        current_headers.extend(new_cols)
        ws.update("1:1", [current_headers], value_input_option="USER_ENTERED")
        
    col_map = {h: i for i, h in enumerate(current_headers)}
    
    name_map = {}
    max_id = 0
    
    for i, row in enumerate(existing):
        n = row.get("Name")
        rid = row.get("ID")
        if n:
            name_map[n] = {"row": i + 2, "id": rid}
            if isinstance(rid, int) and rid > max_id:
                max_id = rid
            elif isinstance(rid, str) and rid.isdigit():
                 if int(rid) > max_id: max_id = int(rid)

    new_rows = []
    processed_heroes_map = {} 

    for h in heroes:
        name = h.get("Name")
        
        # Handle ID logic first
        if name in name_map:
            h_id = name_map[name]["id"]
            row_idx = name_map[name]["row"]
            is_new = False
        else:
            max_id += 1
            h_id = max_id
            is_new = True

        h["ID"] = h_id
        processed_heroes_map[name] = h_id

        # Prepare row based on CURRENT master headers
        row_vals = []
        for col in current_headers:
            val = h.get(col)
            # Fallback for _EN fields using base field (e.g. Overall_EN -> Overall)
            if val is None and col.endswith("_EN"):
                val = h.get(col[:-3])
            
            if val is None: val = ""
            if col == "Icon" and val and isinstance(val, str) and val.startswith("http"):
                val = f'=IMAGE("{val}")'
            row_vals.append(val)
        
        if is_new:
            new_rows.append(row_vals)
        else:
            # Update existing row
            range_name = f"A{row_idx}"
            ws.update(range_name, [row_vals], value_input_option="USER_ENTERED")

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        
    return processed_heroes_map

def update_sub_sheet(sh, sheet_name, data, hero_id_map, priority_fields):
    # Dynamic headers
    headers = get_dynamic_headers(data, priority_fields)
    
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=100, cols=20)
        ws.append_row(headers)
        
    all_rows = ws.get_all_values() 
    if not all_rows:
        ws.append_row(headers)
        all_rows = [headers]
        
    current_headers = all_rows[0]
    
    # Sync headers
    new_cols = [h for h in headers if h not in current_headers]
    if new_cols:
        current_headers.extend(new_cols)
        ws.update("1:1", [current_headers], value_input_option="USER_ENTERED")
        
    # Find ID column index for filtering
    try:
        id_col_idx = current_headers.index("ID")
    except ValueError:
        return # Should not happen

    updated_ids = set(hero_id_map.values())
    
    cleaned_rows = []
    
    # 1. Filter existing rows
    for row in all_rows[1:]:
        if len(row) > id_col_idx:
            try:
                row_hid = int(row[id_col_idx])
            except:
                row_hid = row[id_col_idx]
            if row_hid in updated_ids:
                continue 
        
        # Keep row and pad if needed
        if len(row) < len(current_headers):
            row.extend([""] * (len(current_headers) - len(row)))
        cleaned_rows.append(row)

    # 2. Add new data
    for item in data:
        h_name = item.get("Hero")
        if h_name in hero_id_map:
            real_id = hero_id_map[h_name]
            item["ID"] = real_id
            
            row = []
            for col in current_headers:
                val = item.get(col)
                # Fallback for _EN
                if val is None and col.endswith("_EN"):
                    val = item.get(col[:-3])
                
                if val is None: val = ""
                if col == "Icon" and val and isinstance(val, str) and val.startswith("http"):
                    val = f'=IMAGE("{val}")'
                row.append(val)
            cleaned_rows.append(row)
            
    # Write back
    final_data = [current_headers] + cleaned_rows
    ws.clear()
    ws.update("A1", final_data, value_input_option="USER_ENTERED")

def export_all_data(sheet_id, heroes, skills, engraving, signature, furniture):
    client = authenticate_sheets()
    sh = client.open_by_key(sheet_id)
    
    hero_id_map = update_heroes_sheet(sh, heroes)
    
    update_sub_sheet(sh, "Skills", skills, hero_id_map, 
                     ["ID", "Hero", "Icon", "Unlock Level", "Skill Name", "Type", "Description_EN", "Description_VN"])
                     
    update_sub_sheet(sh, "Engraving Abilities", engraving, hero_id_map, 
                     ["ID", "Hero", "Icon", "Skill Name", "Unlock Level", "Description_EN", "Description_VN"])
                     
    update_sub_sheet(sh, "Signature Item", signature, hero_id_map, 
                     ["ID", "Hero", "Description_EN", "Description_VN"])
                     
    update_sub_sheet(sh, "Furniture Set Bonuses", furniture, hero_id_map, 
                     ["ID", "Hero", "Icon", "Name", "Description_EN", "Description_VN"])
