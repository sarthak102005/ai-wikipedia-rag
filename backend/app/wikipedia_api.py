import requests
from urllib.parse import quote

HEADERS = {
    "User-Agent": "AIWikipediaRAG/1.0 (sarthakmakkar60@gmail.com)"
}


def search_wikipedia(query: str):

    encoded_query = quote(query)

    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_query}"

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=10
        )

        print(response.status_code)

        if response.status_code != 200:
            print(response.text)
            return {
                "error": "No article found."
            }

        data = response.json()

        print(data)

        return {
            "title": data.get("title"),
            "summary": data.get("extract"),
            "url": data.get("content_urls", {})
                     .get("desktop", {})
                     .get("page"),
            "image": data.get("thumbnail", {})
                         .get("source")
        }

    except Exception as e:
        print(e)

        return {
            "error": "Wikipedia request failed."
        }