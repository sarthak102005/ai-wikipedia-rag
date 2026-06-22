import { useState, useEffect, useCallback } from "react";
import "./App.css";

const HISTORY_KEY = "wiki_search_history";
const MAX_HISTORY = 10;

function App() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const [aiQuestion, setAiQuestion] = useState("");
  const [aiAnswer, setAiAnswer] = useState("");
  const [sources, setSources] = useState([]);
  const [askingAI, setAskingAI] = useState(false);

  // Search history — persisted in localStorage
  const [history, setHistory] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
    } catch {
      return [];
    }
  });

  // Persist history whenever it changes
  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  }, [history]);

  const addToHistory = useCallback((term) => {
    if (!term.trim()) return;
    setHistory((prev) => {
      const filtered = prev.filter((h) => h.toLowerCase() !== term.toLowerCase());
      return [term, ...filtered].slice(0, MAX_HISTORY);
    });
  }, []);

  const clearHistory = () => setHistory([]);

  // ── Core search logic (shared by button + history click) ─────────────────

  const doSearch = useCallback(async (searchQuery) => {
    if (!searchQuery.trim()) return;

    setLoading(true);
    setResult(null);
    setAiAnswer("");
    setSources([]);
    setAiQuestion("");

    try {
      const res = await fetch("http://127.0.0.1:8001/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery }),
      });
      const data = await res.json();
      setResult(data);
      if (!data.error) {
        // Store the display title (corrected if applicable) in history
        addToHistory(data.corrected_query || searchQuery);
      }
    } catch {
      setResult({ error: "Failed to connect to backend. Is the server running?" });
    }
    setLoading(false);
  }, [addToHistory]);

  const handleSearch = () => doSearch(query);

  const handleHistoryClick = (term) => {
    setQuery(term);
    doSearch(term);
  };

  // ── Ask AI ────────────────────────────────────────────────────────────────

  const handleAskAI = async () => {
    if (!aiQuestion.trim()) return;
    setAskingAI(true);
    setAiAnswer("");
    setSources([]);

    try {
      const res = await fetch("http://127.0.0.1:8001/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          article: result.full_content || result.summary || "",
          question: aiQuestion,
          title: result.title || "",
        }),
      });
      const data = await res.json();
      setAiAnswer(data.answer || "No answer returned.");
      setSources(data.sources || []);
    } catch {
      setAiAnswer("Failed to connect to the AI service.");
    }
    setAskingAI(false);
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="container">

      {/* ── Header ── */}
      <div className="header">
        <div className="header-badge">⚡ Powered by RAG + Llama 3.1</div>
        <h1>AI Wikipedia Search</h1>
        <p className="header-subtitle">
          Ask questions about any topic — powered by retrieval-augmented generation
        </p>
      </div>

      {/* ── Search bar ── */}
      <div className="search-container">
        <input
          id="search-input"
          className="search-input"
          type="text"
          placeholder="Search any topic  (e.g. Virat Kohli, Black holes, C++)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />
        <button id="search-button" className="search-button" onClick={handleSearch}>
          Search →
        </button>
      </div>

      {/* ── Search history ── */}
      {history.length > 0 && (
        <div className="history-row">
          <span className="history-label">🕒 Recent searches</span>
          {history.map((term, i) => (
            <button
              key={i}
              className="history-chip"
              onClick={() => handleHistoryClick(term)}
              title={`Search "${term}" (cached)`}
            >
              {term}
            </button>
          ))}
          <button className="history-clear" onClick={clearHistory}>
            Clear
          </button>
        </div>
      )}

      {/* ── Loading ── */}
      {loading && (
        <div className="loading-wrapper">
          <div className="spinner" />
          <span>Searching Wikipedia…</span>
        </div>
      )}

      {/* ── Error ── */}
      {result?.error && (
        <div className="error-message">⚠️ {result.error}</div>
      )}

      {/* ── Results ── */}
      {result && !result.error && (
        <>
          {/* Spell-correction banner */}
          {result.corrected_query && (
            <div className="correction-banner">
              <span className="correction-icon">🔤</span>
              <span>Showing results for <strong>{result.corrected_query}</strong></span>
              <span className="correction-original">
                &nbsp;(you searched: "{result.original_query}")
              </span>
            </div>
          )}

          {/* Article card */}
          <div className="result-card">
            {result.image && (
              <div className="article-image-wrap">
                <img
                  src={result.image}
                  alt={result.title}
                  className="article-image"
                />
              </div>
            )}
            <div className="content">
              <div className="article-meta">
                <span className="meta-tag">📖 Wikipedia</span>
              </div>
              <h2 className="result-title">{result.title}</h2>
              <p className="result-summary">{result.summary}</p>
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

          {/* Ask AI card */}
          <div className="ai-section">
            <div className="ai-section-header">
              <div className="ai-icon">🤖</div>
              <div>
                <div className="ai-section-title">Ask AI</div>
                <div className="ai-section-subtitle">
                  Answers generated from the full Wikipedia article
                </div>
              </div>
            </div>

            <div className="ai-input-row">
              <input
                id="ai-input"
                className="ai-input"
                type="text"
                placeholder="e.g. When was he born? What is the main cause?"
                value={aiQuestion}
                onChange={(e) => setAiQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAskAI()}
              />
              <button
                id="ask-button"
                className="ask-button"
                onClick={handleAskAI}
                disabled={askingAI}
              >
                {askingAI ? "Thinking…" : "Ask AI"}
              </button>
            </div>

            {/* Thinking indicator */}
            {askingAI && (
              <div className="ai-thinking">
                <div className="thinking-dots">
                  <span /><span /><span />
                </div>
                AI is reading the article…
              </div>
            )}

            {/* Answer + Sources */}
            {aiAnswer && (
              <div className="ai-answer">
                <div className="answer-header">
                  <span className="answer-label">✦ AI Answer</span>
                </div>
                <div className="answer-body">{aiAnswer}</div>

                {sources.length > 0 && (
                  <>
                    <div className="sources-header">
                      <span className="sources-label">Sources Used</span>
                      <span className="sources-count">
                        {sources.length} chunk{sources.length > 1 ? "s" : ""}
                      </span>
                    </div>
                    <div className="sources-list">
                      {sources.map((src, i) => (
                        <div key={i} className="source-card">{src}</div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default App;