import wikipediaapi

wiki = wikipediaapi.Wikipedia(
    language="en",
    user_agent="AIWikipediaRAG/1.0 (sarthakmakkar60@gmail.com)"
)


def search_wikipedia(query: str):
    page = wiki.page(query)

    if not page.exists():
        return {
            "error": "No article found."
        }

    return {
        "title": page.title,
        "summary": page.summary[:1000],
        "url": page.fullurl
    }