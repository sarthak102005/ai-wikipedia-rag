import { useState } from "react";
import "./App.css";

function App() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;

    setLoading(true);

    try {
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
    } catch (error) {
      console.error(error);
      alert("Failed to connect to backend.");
    }

    setLoading(false);
  };

  return (
    <div className="container">
      <h1>AI Wikipedia Search</h1>

      <div className="search-container">
        <input
          className="search-input"
          type="text"
          placeholder="Search any topic..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              handleSearch();
            }
          }}
        />

        <button
          className="search-button"
          onClick={handleSearch}
        >
          Search
        </button>
      </div>

      {loading && (
        <h2 style={{ textAlign: "center" }}>
          Searching...
        </h2>
      )}

      {result && !result.error && (
        <div className="result-card">
          {result.image && (
            <img
              src={result.image}
              alt={result.title}
              className="article-image"
            />
          )}

          <div className="content">
            <h2 className="result-title">
              {result.title}
            </h2>

            <p className="result-summary">
              {result.summary}
            </p>

            <a
              href={result.url}
              target="_blank"
              rel="noreferrer"
              className="read-link"
            >
              Read Full Article →
            </a>
          </div>
        </div>
      )}

      {result && result.error && (
        <div
          style={{
            textAlign: "center",
            color: "red",
            marginTop: "30px",
            fontSize: "22px",
          }}
        >
          {result.error}
        </div>
      )}
    </div>
  );
}

export default App;