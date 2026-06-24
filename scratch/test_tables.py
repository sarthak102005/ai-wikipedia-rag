import requests
import wikitextparser as wtp
import re

HEADERS = {"User-Agent": "AIWikipediaRAG/1.0 (sarthakmakkar60@gmail.com)"}

def test_fetch_tables(title):
    url = "https://en.wikipedia.org/w/api.php"
    resp = requests.get(url, params={
        "action": "query",
        "prop": "revisions",
        "titles": title,
        "rvprop": "content",
        "rvslots": "main",
        "format": "json",
        "redirects": 1,
    }, headers=HEADERS, timeout=25)
    
    print("Status code:", resp.status_code)
    data = resp.json()
    pages = data.get("query", {}).get("pages", {})
    
    wikitext = ""
    for page in pages.values():
        revisions = page.get("revisions", [])
        if revisions:
            slot = revisions[0].get("slots", {}).get("main", {})
            wikitext = slot.get("*", "")
            break
            
    print("Wikitext length:", len(wikitext))
    if not wikitext:
        print("Error: No wikitext fetched!")
        return
        
    print("\n--- First 1000 characters of wikitext ---")
    print(wikitext[:1000])
    
    table_starts = [m.start() for m in re.finditer(r'\{\|', wikitext)]
    print("\nNumber of '{|' table starts found:", len(table_starts))
        
    parsed = wtp.parse(wikitext)
    print("Number of tables found by wikitextparser:", len(parsed.tables))

test_fetch_tables("Virat Kohli")
