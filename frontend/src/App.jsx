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

  // RAG Pipeline Statistics
  const [totalChunks, setTotalChunks] = useState(0);
  const [retrievedChunks, setRetrievedChunks] = useState(0);
  const [cacheHit, setCacheHit] = useState(false);
  const [responseTime, setResponseTime] = useState("");

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
    setTotalChunks(0);
    setRetrievedChunks(0);
    setCacheHit(false);
    setResponseTime("");

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
    setTotalChunks(0);
    setRetrievedChunks(0);
    setCacheHit(false);
    setResponseTime("");

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
      setTotalChunks(data.total_chunks || 0);
      setRetrievedChunks(data.retrieved_chunks || 0);
      setCacheHit(!!data.cache_hit);
      setResponseTime(data.time || "");
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
        result.error.includes("No Wikipedia article found") ? (
          <div className="not-found-card">
            <div className="not-found-icon">🔍</div>
            <h3 className="not-found-title">Topic Not Found</h3>
            <p className="not-found-text">{result.error}</p>
            <div className="search-tips">
              <strong>Search Tips:</strong>
              <ul>
                <li>Double check spelling (though we auto-correct most typos!).</li>
                <li>Try broader terms instead of complete question queries.</li>
                <li>Make sure you use English Wikipedia terms.</li>
              </ul>
            </div>
          </div>
        ) : (
          <div className="error-message">⚠️ {result.error}</div>
        )
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
                {/* Statistics Panel */}
                <div className="stats-panel">
                  <div className="stats-card">
                    <span className="stats-val">{totalChunks}</span>
                    <span className="stats-lbl">Chunks Created</span>
                  </div>
                  <div className="stats-card">
                    <span className="stats-val">{retrievedChunks}</span>
                    <span className="stats-lbl">Retrieved</span>
                  </div>
                  <div className="stats-card">
                    <span className={`badge ${cacheHit ? "cache-hit" : "cache-miss"}`}>
                      {cacheHit ? "🟢 Cache HIT" : "🔵 Fresh Gen"}
                    </span>
                    <span className="stats-lbl">Cache Status</span>
                  </div>
                  <div className="stats-card">
                    <span className="stats-val time-val">⚡ {responseTime}</span>
                    <span className="stats-lbl">Response Time</span>
                  </div>
                </div>

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
                        <div key={i} className="source-card">
                          <div className="source-card-header">
                            <span className="source-index">Source {i + 1}</span>
                            <span className="source-score">Similarity: {Math.round(src.score * 100)}%</span>
                          </div>
                          <div className="source-text">{src.text}</div>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {/* How the AI Answered */}
                <div className="explanation-section">
                  <h4 className="explanation-title">How the AI Answered</h4>
                  <ul className="explanation-list">
                    <li className="explanation-item done">✓ Split article into {totalChunks} chunks (500 chars, 100 overlap)</li>
                    <li className="explanation-item done">✓ Generated sentence embeddings via all-MiniLM-L6-v2</li>
                    <li className="explanation-item done">✓ Loaded FAISS index & retrieved top {retrievedChunks} chunks</li>
                    <li className="explanation-item done">✓ Filtered chunks below 30% cosine similarity threshold</li>
                    <li className="explanation-item done">
                      {cacheHit 
                        ? "✓ Served answer immediately from SQLite persistent cache" 
                        : "✓ Sent context to LLM (Llama 3.1) and generated final answer"
                      }
                    </li>
                  </ul>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default App;