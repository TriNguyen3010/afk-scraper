from fastapi import FastAPI, BackgroundTasks, HTTPException, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List
import os
import asyncio
from functools import partial
import scraper_service

app = FastAPI()

# Mount static files (Frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

class ScrapeRequest(BaseModel):
    urls: List[str]

class FetchHeroesRequest(BaseModel):
    urls: List[str]

# ... (global vars) ...

@app.post("/api/fetch_heroes")
def fetch_heroes(request: FetchHeroesRequest):
    all_links = []
    for url in request.urls:
        if not url: continue
        links = scraper_service.extract_hero_links(url)
        all_links.extend(links)
    
    # Remove duplicates
    unique_links = list(dict.fromkeys(all_links))
    
    if not unique_links:
        raise HTTPException(status_code=404, detail="No heroes found or invalid URLs")
    return {"heroes": unique_links}

# Global variable to store last generated file path (simple implementation)
last_generated_file = None

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

import google_sheets_service

# ... (existing imports)

@app.websocket("/ws/scrape")
async def websocket_endpoint(websocket: WebSocket):
    global last_generated_file
    await websocket.accept()
    
    try:
        data = await websocket.receive_json()
        urls = data.get("urls", [])
        export_type = data.get("export_type", "excel")
        sheet_id = data.get("sheet_id", "")
        # Validation for Google Sheet
        if export_type == "google_sheet":
            if not sheet_id:
                await websocket.send_json({"type": "error", "message": "Google Sheet ID is required."})
                return
            if not os.path.exists("service_account.json"):
                await websocket.send_json({"type": "error", "message": "Missing 'service_account.json' file on server."})
                return

        heroes, all_skills = [], []
        all_engraving, all_signature, all_furniture = [], [], []
        total = len(urls)

        semaphore = asyncio.Semaphore(5) # Limit concurrency to 5
        finished_count = 0

        async def process_url(url):
            nonlocal finished_count
            
            # Notify start (optional, maybe too noisy, let's just notify finish or use a generic "Processing" message)
            # But let's keep it simple.
            
            async with semaphore:
                loop = asyncio.get_running_loop()
                # Run the blocking scrape_page in a thread
                try:
                    result = await loop.run_in_executor(
                        None, 
                        partial(scraper_service.scrape_page, url)
                    )
                except Exception as e:
                    print(f"Error processing {url}: {e}")
                    result = (None, [], [], [], [])

                hero_data, h_skills, h_engr, h_sig, h_furn = result
                
                finished_count += 1
                
                if hero_data:
                    msg = f"Completed {hero_data.get('Name', 'Unknown')}"
                else:
                    msg = f"Failed: {url}"

                await websocket.send_json({
                    "type": "progress", 
                    "current": finished_count, 
                    "total": total, 
                    "message": msg
                })
                return result

        # Launch all tasks
        tasks = [process_url(url) for url in urls]
        results = await asyncio.gather(*tasks)

        # Aggregate results
        for res in results:
            hero_data, h_skills, h_engr, h_sig, h_furn = res
            if hero_data:
                # Append raw data, IDs are handled in export step
                heroes.append(hero_data)
                all_skills.extend(h_skills)
                all_engraving.extend(h_engr)
                all_signature.extend(h_sig)
                all_furniture.extend(h_furn)

        if not heroes:
            await websocket.send_json({"type": "error", "message": "No data found or all scrapes failed."})
            return

        # Export phase
        if export_type == "google_sheet":
            await websocket.send_json({
                "type": "progress", 
                "current": total, 
                "total": total, 
                "message": "Writing to Google Sheet..."
            })
            try:
                google_sheets_service.export_all_data(sheet_id, heroes, all_skills, all_engraving, all_signature, all_furniture)
                await websocket.send_json({
                    "type": "complete", 
                    "mode": "google_sheet",
                    "sheet_id": sheet_id,
                    "hero_count": len(heroes)
                })
            except Exception as e:
                import traceback
                error_msg = f"Google Sheet Error: {repr(e)}\n\nTraceback:\n{traceback.format_exc()}"
                print(error_msg) # Print to server logs
                await websocket.send_json({"type": "error", "message": error_msg})

        else:
            # Excel fallback
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"afk_arena_data_{timestamp}.xlsx"
            filepath = os.path.join(os.getcwd(), filename)
            scraper_service.create_excel(heroes, all_skills, all_engraving, all_signature, all_furniture, filepath)
            
            last_generated_file = filename
            
            await websocket.send_json({
                "type": "complete", 
                "mode": "excel",
                "filename": filename, 
                "hero_count": len(heroes)
            })

    except Exception as e:
        print(f"WebSocket Error: {e}")
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()

@app.get("/api/download/{filename}")
def download_file(filename: str):
    file_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    raise HTTPException(status_code=404, detail="File not found")
