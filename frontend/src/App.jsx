import { useState, useEffect, useCallback } from "react";
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

/* ── Reusable animation variants ─────────────────────────────────────── */
const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.07, duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  }),
  exit: { opacity: 0, y: -16, transition: { duration: 0.25 } },
};

const scaleIn = {
  hidden: { opacity: 0, scale: 0.88 },
  visible: (i = 0) => ({
    opacity: 1,
    scale: 1,
    transition: { delay: i * 0.06, duration: 0.4, ease: [0.22, 1, 0.36, 1] },
  }),
  exit: { opacity: 0, scale: 0.92, transition: { duration: 0.2 } },
};

const slideRight = {
  hidden: { opacity: 0, x: -20 },
  visible: (i = 0) => ({
    opacity: 1,
    x: 0,
    transition: { delay: i * 0.05, duration: 0.35, ease: "easeOut" },
  }),
  exit: { opacity: 0, x: 20, transition: { duration: 0.2 } },
};

/* ── Animated counter ─────────────────────────────────────────────────── */
function AnimatedNumber({ value }) {
  const motionVal = useMotionValue(0);
  const spring = useSpring(motionVal, { stiffness: 80, damping: 18 });
  const rounded = useTransform(spring, (v) => Math.round(v));
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    motionVal.set(value);
  }, [value, motionVal]);

  useEffect(() => {
    return rounded.on("change", setDisplay);
  }, [rounded]);

  return <span>{display}</span>;
}

/* ── Main App ─────────────────────────────────────────────────────────── */
function App() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const [aiQuestion, setAiQuestion] = useState("");
  const [aiAnswer, setAiAnswer] = useState("");
  const [sources, setSources] = useState([]);
  const [askingAI, setAskingAI] = useState(false);

  const [totalChunks, setTotalChunks] = useState(0);
  const [retrievedChunks, setRetrievedChunks] = useState(0);
  const [cacheHit, setCacheHit] = useState(false);
  const [responseTime, setResponseTime] = useState("");

  const [history, setHistory] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
    } catch {
      return [];
    }
  });

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

  const doSearch = useCallback(
    async (searchQuery) => {
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
        if (!data.error) addToHistory(data.corrected_query || searchQuery);
      } catch {
        setResult({ error: "Failed to connect to backend. Is the server running?" });
      }
      setLoading(false);
    },
    [addToHistory]
  );

  const handleSearch = () => doSearch(query);
  const handleHistoryClick = (term) => {
    setQuery(term);
    doSearch(term);
  };

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

  /* ── Render ─────────────────────────────────────────────────────────── */
  return (
    <>
      {/* Background Glows */}
      <div className="bg-glows">
        <div className="glow-circle glow-1" />
        <div className="glow-circle glow-2" />
        <div className="glow-circle glow-3" />
      </div>

      <div className="container">

        {/* ── Header ── */}
        <motion.div
          className="header"
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.12 } },
          }}
        >
          <motion.div className="header-badge" variants={fadeUp}>
            ⚡ Powered by RAG + Llama 3.1
          </motion.div>
          <motion.h1 variants={fadeUp}>AI Wikipedia Search</motion.h1>
          <motion.p className="header-subtitle" variants={fadeUp}>
            Ask questions about any topic — powered by retrieval-augmented generation
          </motion.p>
        </motion.div>

        {/* ── Search bar ── */}
        <motion.div
          className="search-container"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        >
          <input
            id="search-input"
            className="search-input"
            type="text"
            placeholder="Search any topic  (e.g. Virat Kohli, Black holes, C++)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <motion.button
            id="search-button"
            className="search-button"
            onClick={handleSearch}
            whileHover={{ scale: 1.04, translateY: -2 }}
            whileTap={{ scale: 0.96 }}
            transition={{ type: "spring", stiffness: 350, damping: 20 }}
          >
            Search →
          </motion.button>
        </motion.div>

        {/* ── Search history ── */}
        <AnimatePresence>
          {history.length > 0 && (
            <motion.div
              className="history-row"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3 }}
            >
              <span className="history-label">🕒 Recent searches</span>
              {history.map((term, i) => (
                <motion.button
                  key={term}
                  className="history-chip"
                  onClick={() => handleHistoryClick(term)}
                  title={`Search "${term}" (cached)`}
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

        {/* ── Error ── */}
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

        {/* ── Results ── */}
        <AnimatePresence>
          {result && !result.error && (
            <motion.div
              key="results"
              initial="hidden"
              animate="visible"
              exit="exit"
              variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.1 } } }}
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

              {/* Article card */}
              <motion.div className="result-card" variants={fadeUp} whileHover={{ y: -4, boxShadow: "0 16px 48px rgba(0,0,0,0.6), 0 0 40px rgba(99,102,241,0.18)" }} transition={{ type: "spring", stiffness: 300, damping: 24 }}>
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
                      whileHover={{ scale: 1.04 }}
                      transition={{ duration: 0.35 }}
                    />
                  </motion.div>
                )}
                <div className="content">
                  <motion.div
                    className="article-meta"
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.25 }}
                  >
                    <span className="meta-tag">📖 Wikipedia</span>
                  </motion.div>
                  <motion.h2
                    className="result-title"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3, duration: 0.4 }}
                  >
                    {result.title}
                  </motion.h2>
                  <motion.p
                    className="result-summary"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.4, duration: 0.5 }}
                  >
                    {result.summary}
                  </motion.p>
                  <motion.a
                    href={result.url}
                    target="_blank"
                    rel="noreferrer"
                    className="read-link"
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.5 }}
                    whileHover={{ x: 5, scale: 1.03 }}
                  >
                    Read Full Article →
                  </motion.a>
                </div>
              </motion.div>

              {/* Ask AI card */}
              <motion.div className="ai-section" variants={fadeUp}>
                <div className="ai-section-header">
                  <motion.div
                    className="ai-icon"
                    animate={{ rotate: [0, 5, -5, 0] }}
                    transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                  >
                    🤖
                  </motion.div>
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
                  <motion.button
                    id="ask-button"
                    className="ask-button"
                    onClick={handleAskAI}
                    disabled={askingAI}
                    whileHover={!askingAI ? { scale: 1.05, y: -2 } : {}}
                    whileTap={!askingAI ? { scale: 0.97 } : {}}
                    transition={{ type: "spring", stiffness: 350, damping: 20 }}
                  >
                    {askingAI ? "Thinking…" : "Ask AI"}
                  </motion.button>
                </div>

                {/* Thinking indicator */}
                <AnimatePresence>
                  {askingAI && (
                    <motion.div
                      className="ai-thinking"
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.3 }}
                    >
                      <div className="thinking-dots">
                        <span /><span /><span />
                      </div>
                      AI is reading the article…
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Answer + Sources */}
                <AnimatePresence>
                  {aiAnswer && (
                    <motion.div
                      className="ai-answer"
                      key="ai-answer"
                      initial={{ opacity: 0, y: 20, scale: 0.97 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -10 }}
                      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                    >
                      {/* Statistics Panel */}
                      <motion.div
                        className="stats-panel"
                        initial="hidden"
                        animate="visible"
                        variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.08 } } }}
                      >
                        {[
                          { val: totalChunks, label: "Chunks Created", isNum: true },
                          { val: retrievedChunks, label: "Retrieved", isNum: true },
                          {
                            val: null,
                            label: "Cache Status",
                            isNum: false,
                            badge: true,
                          },
                          { val: null, label: "Response Time", isNum: false, time: true },
                        ].map((item, i) => (
                          <motion.div
                            key={i}
                            className="stats-card"
                            custom={i}
                            variants={scaleIn}
                            whileHover={{ scale: 1.05, y: -2 }}
                          >
                            {item.isNum && (
                              <span className="stats-val">
                                <AnimatedNumber value={item.val} />
                              </span>
                            )}
                            {item.badge && (
                              <span className={`badge ${cacheHit ? "cache-hit" : "cache-miss"}`}>
                                {cacheHit ? "🟢 Cache HIT" : "🔵 Fresh Gen"}
                              </span>
                            )}
                            {item.time && (
                              <span className="stats-val time-val">⚡ {responseTime}</span>
                            )}
                            <span className="stats-lbl">{item.label}</span>
                          </motion.div>
                        ))}
                      </motion.div>

                      <div className="answer-header">
                        <motion.span
                          className="answer-label"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: 0.3 }}
                        >
                          ✦ AI Answer
                        </motion.span>
                      </div>
                      <motion.div
                        className="answer-body"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.25, duration: 0.5 }}
                      >
                        {aiAnswer}
                      </motion.div>

                      {sources.length > 0 && (
                        <>
                          <div className="sources-header">
                            <span className="sources-label">Sources Used</span>
                            <span className="sources-count">
                              {sources.length} chunk{sources.length > 1 ? "s" : ""}
                            </span>
                          </div>
                          <motion.div
                            className="sources-list"
                            initial="hidden"
                            animate="visible"
                            variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.07 } } }}
                          >
                            {sources.map((src, i) => (
                              <motion.div
                                key={i}
                                className="source-card"
                                custom={i}
                                variants={slideRight}
                                whileHover={{ x: 4, backgroundColor: "rgba(255,255,255,0.05)" }}
                              >
                                <div className="source-card-header">
                                  <span className="source-index">Source {i + 1}</span>
                                  <motion.span
                                    className="source-score"
                                    initial={{ opacity: 0, scale: 0.8 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    transition={{ delay: 0.15 + i * 0.07 }}
                                  >
                                    Similarity: {Math.round(src.score * 100)}%
                                  </motion.span>
                                </div>
                                <div className="source-text">{src.text}</div>
                              </motion.div>
                            ))}
                          </motion.div>
                        </>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}

export default App;