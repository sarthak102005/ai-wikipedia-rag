import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "AIWikipediaRAG/1.0 (sarthakmakkar60@gmail.com)"}

def test_html_tables(title):
    url = "https://en.wikipedia.org/w/api.php"
    resp = requests.get(url, params={
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "redirects": 1,
    }, headers=HEADERS, timeout=25)
    
    print("Status code:", resp.status_code)
    data = resp.json()
    html_content = data.get("parse", {}).get("text", {}).get("*", "")
    print("HTML length:", len(html_content))
    
    if not html_content:
        print("Error: No HTML fetched!")
        return
        
    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table")
    print("Number of HTML tables found:", len(tables))
    
    for i, table in enumerate(tables[:5]):
        print(f"\n--- HTML Table {i+1} ---")
        
        # Try to find class and caption
        classes = table.get("class", [])
        print("Classes:", classes)
        
        caption_tag = table.find("caption")
        caption = caption_tag.text.strip() if caption_tag else "No caption"
        print("Caption:", caption)
        
        # Extract headers and rows
        rows = []
        for tr in table.find_all("tr"):
            cells = [cell.text.strip() for cell in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
                
        print("Rows count:", len(rows))
        if rows:
            print("First 3 rows:")
            for r in rows[:3]:
                print("  ", r)

test_html_tables("Virat Kohli")
