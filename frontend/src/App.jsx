import { useState, useEffect, useCallback, useRef } from "react";
import {
  motion,
  AnimatePresence,
  useSpring,
  useTransform,
  useMotionValue,
} from "framer-motion";
import "./App.css";

const HISTORY_KEY = "wiki_search_history";
const MAX_HISTORY = 10;
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8001" : "");

/* ── Animation variants ──────────────────────────────────────────────────── */
const fadeUp = {
  hidden:  { opacity: 0, y: 24 },
  visible: (i = 0) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.07, duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  }),
  exit: { opacity: 0, y: -16, transition: { duration: 0.25 } },
};

const scaleIn = {
  hidden:  { opacity: 0, scale: 0.88 },
  visible: (i = 0) => ({
    opacity: 1, scale: 1,
    transition: { delay: i * 0.06, duration: 0.4, ease: [0.22, 1, 0.36, 1] },
  }),
  exit: { opacity: 0, scale: 0.92, transition: { duration: 0.2 } },
};

const slideRight = {
  hidden:  { opacity: 0, x: -20 },
  visible: (i = 0) => ({
    opacity: 1, x: 0,
    transition: { delay: i * 0.05, duration: 0.35, ease: "easeOut" },
  }),
  exit: { opacity: 0, x: 20, transition: { duration: 0.2 } },
};

/* ── Disambiguation View ─────────────────────────────────────────────────── */
function DisambiguationView({ result, doSearch, setQuery }) {
  const [filterText, setFilterText] = useState("");

  const filteredOptions = (result.options || []).filter(
    (opt) =>
      opt.title.toLowerCase().includes(filterText.toLowerCase()) ||
      opt.description.toLowerCase().includes(filterText.toLowerCase())
  );

  return (
    <motion.div
      className="disambiguation-card"
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="disambig-header">
        <span className="disambig-badge">🔍 Disambiguation</span>
        <h2 className="disambig-title">{result.title}</h2>
        <p className="disambig-subtitle">
          The topic you searched for is ambiguous. Please select one of the
          specific articles below:
        </p>
      </div>

      <div className="disambig-filter-wrapper">
        <input
          type="text"
          className="disambig-filter-input"
          placeholder="🔍 Filter options (e.g. cricketer, road, film)..."
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
        />
        {filterText && (
          <span className="disambig-filter-count">
            Found {filteredOptions.length} of {result.options.length}
          </span>
        )}
      </div>

      <div className="disambig-options-grid">
        {filteredOptions.length > 0 ? (
          filteredOptions.map((opt, idx) => (
            <motion.div
              key={idx}
              className="disambig-option-card"
              onClick={() => {
                setQuery(opt.title);
                doSearch(opt.title);
              }}
              whileHover={{
                scale: 1.015,
                backgroundColor: "rgba(79,142,247,0.08)",
                borderColor: "rgba(79,142,247,0.4)",
              }}
              whileTap={{ scale: 0.995 }}
            >
              <h3 className="disambig-option-title">{opt.title}</h3>
              <p className="disambig-option-desc">{opt.description}</p>
            </motion.div>
          ))
        ) : (
          <div className="disambig-no-results">
            No matching options found. Try checking your spelling or search
            filter.
          </div>
        )}
      </div>
    </motion.div>
  );
}

/* ── Typing indicator ────────────────────────────────────────────────────── */
function TypingIndicator() {
  return (
    <div className="msg-row msg-assistant">
      <div className="msg-bubble assistant-bubble typing-bubble">
        <div className="typing-dots">
          <span />
          <span />
          <span />
        </div>
        <span className="typing-label">AI is reading the article…</span>
      </div>
    </div>
  );
}

/* ── Main App ────────────────────────────────────────────────────────────── */
export default function App() {
  const [query, setQuery]   = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const [aiQuestion, setAiQuestion] = useState("");
  const [askingAI, setAskingAI]     = useState(false);

  /* Chat state */
  const [messages, setMessages] = useState([]);
  const [conversationHistory, setConversationHistory] = useState([]);

  /* Article assets */
  const [images, setImages]   = useState([]);
  const [tables, setTables]   = useState([]);

  /* Search history */
  const [history, setHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; }
    catch { return []; }
  });

  /* Auto-scroll ref */
  const messagesEndRef = useRef(null);
  const chatInputRef   = useRef(null);

  /* Persist history */
  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  }, [history]);

  /* Auto-scroll to bottom when messages change */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, askingAI]);

  const addToHistory = useCallback((term) => {
    if (!term.trim()) return;
    setHistory((prev) => {
      const filtered = prev.filter(
        (h) => h.toLowerCase() !== term.toLowerCase()
      );
      return [term, ...filtered].slice(0, MAX_HISTORY);
    });
  }, []);

  const clearHistory = () => setHistory([]);

  /* ── Search ─────────────────────────────────────────────────────────────── */
  const doSearch = useCallback(
    async (searchQuery) => {
      if (!searchQuery.trim()) return;
      setLoading(true);
      setResult(null);
      setImages([]);
      setTables([]);
      setMessages([]);
      setConversationHistory([]);

      try {
        const res = await fetch(`${API_BASE_URL}/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: searchQuery }),
        });
        const data = await res.json();
        setResult(data);
        if (!data.error) {
          addToHistory(data.corrected_query || searchQuery);
          setImages(data.images || []);
          setTables(data.tables || []);
        }
      } catch {
        setResult({
          error: "Failed to connect to backend. Is the server running?",
        });
      }
      setLoading(false);
    },
    [addToHistory]
  );

  const handleSearch       = () => doSearch(query);
  const handleHistoryClick = (term) => { setQuery(term); doSearch(term); };

  /* ── Ask AI ──────────────────────────────────────────────────────────────── */
  const handleAskAI = async () => {
    const q = aiQuestion.trim();
    if (!q || !result) return;

    setAskingAI(true);
    setAiQuestion("");

    /* Add user bubble immediately */
    setMessages((prev) => [
      ...prev,
      { role: "user", content: q, time: new Date().toISOString() },
    ]);

    try {
      const res = await fetch(`${API_BASE_URL}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          article:  result.full_content || result.summary || "",
          question: q,
          title:    result.title || "",
          images,
          tables,
          conversation_history: conversationHistory,
        }),
      });
      const data = await res.json();

      const assistantMsg = {
        role:          "assistant",
        content:       data.answer || "No answer returned.",
        image:         data.related_image || null,
        confidence:    data.confidence_score || 0.0,
        time:          data.time || "",
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setConversationHistory((prev) => [
        ...prev,
        { question: q, answer: assistantMsg.content },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role:    "assistant",
          content: "Failed to connect to the AI service.",
          image:   null,
          confidence: 0.0,
          time:    "",
        },
      ]);
    }

    setAskingAI(false);
    setTimeout(() => chatInputRef.current?.focus(), 100);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAskAI();
    }
  };

  /* ── Render ──────────────────────────────────────────────────────────────── */
  return (
    <>
      {/* Ambient background glows */}
      <div className="bg-glows">
        <div className="glow-circle glow-1" />
        <div className="glow-circle glow-2" />
        <div className="glow-circle glow-3" />
        <div className="glow-circle glow-4" />
      </div>

      <div className="app-wrapper">
        {/* ── Header ── */}
        <motion.header
          className="app-header"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="header-badge">⚡ Powered by Wikipedia + AI</div>
          <h1 className="app-title">AI Wikipedia Search</h1>
          <p className="app-subtitle">
            Search any topic — then chat with the AI about it
          </p>
        </motion.header>

        {/* ── Search bar ── */}
        <motion.div
          className="search-container"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        >
          <input
            id="search-input"
            className="search-input"
            type="text"
            placeholder="Search any Wikipedia topic to begin — then ask the AI anything about it"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <div className="search-button-group">
            <motion.button
              id="search-button"
              className="search-btn"
              onClick={handleSearch}
              whileHover={{ scale: 1.04, translateY: -2 }}
              whileTap={{ scale: 0.96 }}
              transition={{ type: "spring", stiffness: 350, damping: 20 }}
            >
              Search →
            </motion.button>
            <motion.button
              className="search-secondary-btn"
              onClick={() => doSearch("Mount Everest")}
              whileHover={{ scale: 1.02, translateY: -1 }}
              whileTap={{ scale: 0.98 }}
            >
              Try Mount Everest
            </motion.button>
          </div>
        </motion.div>

        {/* ── Recent searches ── */}
        <AnimatePresence>
          {history.length > 0 && (
            <motion.div
              className="history-row"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3 }}
            >
              <span className="history-label">🕒 Recent</span>
              {history.map((term, i) => (
                <motion.button
                  key={term}
                  className="history-chip"
                  onClick={() => handleHistoryClick(term)}
                  title={`Search "${term}"`}
                  custom={i}
                  variants={slideRight}
                  initial="hidden"
                  animate="visible"
                  exit="exit"
                  whileHover={{ scale: 1.07, y: -2 }}
                  whileTap={{ scale: 0.95 }}
                >
                  {term}
                </motion.button>
              ))}
              <motion.button
                className="history-clear"
                onClick={clearHistory}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                Clear
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Loading ── */}
        <AnimatePresence>
          {loading && (
            <motion.div
              className="loading-wrapper"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.85 }}
              transition={{ duration: 0.3 }}
            >
              <div className="spinner" />
              <motion.span
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
              >
                Searching Wikipedia…
              </motion.span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Error states ── */}
        <AnimatePresence>
          {result?.error && (
            result.error.includes("No Wikipedia article found") ? (
              <motion.div
                className="not-found-card"
                key="not-found"
                variants={scaleIn}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                <motion.div
                  className="not-found-icon"
                  animate={{ rotate: [0, -10, 10, -10, 0] }}
                  transition={{ delay: 0.3, duration: 0.6 }}
                >
                  🔍
                </motion.div>
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
              </motion.div>
            ) : (
              <motion.div
                className="error-message"
                key="error"
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                ⚠️ {result.error}
              </motion.div>
            )
          )}
        </AnimatePresence>

        {/* ── Results area ── */}
        <AnimatePresence>
          {result && !result.error && (
            <motion.div
              key="results"
              initial="hidden"
              animate="visible"
              exit="exit"
              variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.08 } } }}
            >
              {/* Spell-correction banner */}
              {result.corrected_query && (
                <motion.div className="correction-banner" variants={fadeUp}>
                  <span className="correction-icon">🔤</span>
                  <span>
                    Showing results for <strong>{result.corrected_query}</strong>
                  </span>
                  <span className="correction-original">
                    &nbsp;(you searched: "{result.original_query}")
                  </span>
                </motion.div>
              )}

              {result.is_disambiguation ? (
                /* Disambiguation */
                <DisambiguationView
                  result={result}
                  doSearch={doSearch}
                  setQuery={setQuery}
                />
              ) : (
                <>
                  {/* ── Article card — image + wiki link chip ── */}
                  <motion.div
                    className="article-card"
                    variants={fadeUp}
                    whileHover={{
                      y: -3,
                      boxShadow:
                        "0 16px 48px rgba(0,0,0,0.6), 0 0 40px rgba(79,142,247,0.14)",
                    }}
                    transition={{ type: "spring", stiffness: 300, damping: 24 }}
                  >
                    {result.image && (
                      <motion.div
                        className="article-image-wrap"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.2 }}
                      >
                        <motion.img
                          src={result.image}
                          alt={result.title}
                          className="article-image"
                          whileHover={{ scale: 1.03 }}
                          transition={{ duration: 0.35 }}
                        />
                      </motion.div>
                    )}
                    <div className="article-card-body">
                      <div className="article-meta">
                        <span className="meta-tag">📖 Wikipedia</span>
                      </div>
                      <h2 className="article-title">{result.title}</h2>
                      <a
                        href={result.url}
                        target="_blank"
                        rel="noreferrer"
                        className="wiki-link-chip"
                      >
                        🌐 View on Wikipedia →
                      </a>
                    </div>
                  </motion.div>

                  {/* ── Image gallery ── */}
                  {images.length > 0 && (
                    <motion.div className="gallery-section" variants={fadeUp}>
                      <div className="gallery-header">
                        <span className="gallery-label">
                          📸 Images from this article
                        </span>
                        <span className="gallery-count">
                          {images.length} images
                        </span>
                      </div>
                      <div className="gallery-scroll">
                        {images.map((img, i) => (
                          <motion.div
                            key={i}
                            className="gallery-item"
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: i * 0.04, duration: 0.35 }}
                            whileHover={{ scale: 1.04, y: -4 }}
                          >
                            <div className="gallery-img-wrap">
                              <img src={img.url} alt={img.caption || 'Article image'} />
                            </div>
                            <div className="gallery-caption-static">
                              {img.caption}
                            </div>
                          </motion.div>
                        ))}
                      </div>
                    </motion.div>
                  )}

                  {/* ── Chat interface ── */}
                  <motion.div className="chat-section" variants={fadeUp}>
                    {/* Chat header */}
                    <div className="chat-header">
                      <div className="chat-header-left">
                        <motion.div
                          className="chat-ai-icon"
                          animate={{ rotate: [0, 5, -5, 0] }}
                          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                        >
                          🤖
                        </motion.div>
                        <div>
                          <div className="chat-title">Ask AI</div>
                          <div className="chat-subtitle">
                            Answers sourced from the full Wikipedia article
                          </div>
                        </div>
                      </div>
                      {messages.length > 0 && (
                        <button
                          className="chat-clear-btn"
                          onClick={() => {
                            setMessages([]);
                            setConversationHistory([]);
                          }}
                        >
                          Clear chat
                        </button>
                      )}
                    </div>

                    {/* Messages list */}
                    <div className="messages-list" id="messages-list">
                      {messages.length === 0 && (
                        <div className="msg-empty">
                          <span className="msg-empty-icon">💬</span>
                          <p>Ask anything about <strong>{result.title}</strong></p>
                          <p className="msg-empty-hint">
                            Try: "Who is this?", "When was it founded?", "What are the key facts?"
                          </p>
                        </div>
                      )}

                      {messages.map((m, i) =>
                        m.role === "user" ? (
                          <motion.div
                            key={i}
                            className="msg-row msg-user"
                            initial={{ opacity: 0, x: 20 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ duration: 0.3, ease: "easeOut" }}
                          >
                            <div className="msg-bubble user-bubble">
                              {m.content}
                            </div>
                          </motion.div>
                        ) : (
                          <motion.div
                            key={i}
                            className="msg-row msg-assistant"
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ duration: 0.3, ease: "easeOut" }}
                          >
                            <div className="msg-bubble assistant-bubble">
                              <div
                                className="msg-answer-text"
                                dangerouslySetInnerHTML={{ __html: m.content }}
                              />
                              {m.image && (
                                <div className="chat-response-image">
                                  <img
                                    src={m.image.url}
                                    alt={m.image.caption}
                                  />
                                  {m.image.caption && (
                                    <p className="image-caption">
                                      {m.image.caption}
                                    </p>
                                  )}
                                </div>
                              )}
                              <div className="msg-meta">
                                {m.confidence > 0 && (
                                  <span className="msg-confidence">
                                    {Math.round(m.confidence * 100)}% confidence
                                  </span>
                                )}
                                {m.time && (
                                  <span className="msg-time">• {m.time}</span>
                                )}
                              </div>
                            </div>
                          </motion.div>
                        )
                      )}

                      {/* Typing indicator */}
                      <AnimatePresence>
                        {askingAI && (
                          <motion.div
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -10 }}
                            transition={{ duration: 0.25 }}
                          >
                            <TypingIndicator />
                          </motion.div>
                        )}
                      </AnimatePresence>

                      {/* Scroll anchor */}
                      <div ref={messagesEndRef} />
                    </div>

                    {/* Chat input */}
                    <div className="chat-input-bar">
                      <textarea
                        ref={chatInputRef}
                        className="chat-textarea"
                        placeholder={`Ask anything about ${result.title}…`}
                        value={aiQuestion}
                        onChange={(e) => setAiQuestion(e.target.value)}
                        onKeyDown={handleKeyDown}
                        rows={1}
                        disabled={askingAI}
                      />
                      <motion.button
                        className="send-btn"
                        onClick={handleAskAI}
                        disabled={askingAI || !aiQuestion.trim()}
                        whileHover={
                          !askingAI && aiQuestion.trim()
                            ? { scale: 1.08, y: -1 }
                            : {}
                        }
                        whileTap={
                          !askingAI && aiQuestion.trim() ? { scale: 0.95 } : {}
                        }
                        transition={{ type: "spring", stiffness: 400, damping: 20 }}
                      >
                        {askingAI ? (
                          <div className="send-spinner" />
                        ) : (
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                            <path
                              d="M22 2L11 13"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                            <path
                              d="M22 2L15 22L11 13L2 9L22 2Z"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        )}
                      </motion.button>
                    </div>
                  </motion.div>
                </>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}