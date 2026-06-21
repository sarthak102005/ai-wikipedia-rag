import { useState } from "react";
import "./App.css";

function App() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);

  async function searchWikipedia() {
    if (!query.trim()) return;

    const response = await fetch("http://127.0.0.1:8001/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query: query,
      }),
    });

    const data = await response.json();

    console.log(data);

    setResult(data);
  }

  return (
    <div className="container">
      <h1>AI Wikipedia Search</h1>

      <div className="search-box">
        <input
          type="text"
          placeholder="Search Wikipedia..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />

        <button onClick={searchWikipedia}>
          Search
        </button>
      </div>

      {result && (
        <div className="result-card">

          <h2>{result.title}</h2>

          <p>{result.summary}</p>

          <a
            href={result.url}
            target="_blank"
            rel="noreferrer"
          >
            Read Full Article →
          </a>

        </div>
      )}

    </div>
  );
}

export default App;