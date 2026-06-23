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

/* ── Animated counter ────────────────────────────────────────────────────── */
function AnimatedNumber({ value }) {
  const motionVal = useMotionValue(0);
  const spring    = useSpring(motionVal, { stiffness: 80, damping: 18 });
  const rounded   = useTransform(spring, (v) => Math.round(v));
  const [display, setDisplay] = useState(0);

  useEffect(() => { motionVal.set(value); }, [value, motionVal]);
  useEffect(() => rounded.on("change", setDisplay), [rounded]);

  return <span>{display}</span>;
}

/* ── Disambiguation View ─────────────────────────────────────────────────── */
function DisambiguationView({ result, doSearch, setQuery }) {
  const [filterText, setFilterText] = useState("");

  const filteredOptions = (result.options || []).filter(opt =>
    opt.title.toLowerCase().includes(filterText.toLowerCase()) ||
    opt.description.toLowerCase().includes(filterText.toLowerCase())
  );

  return (
    <motion.div className="disambiguation-card"
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -2, boxShadow: "0 16px 48px rgba(0,0,0,0.6), 0 0 40px rgba(99,102,241,0.12)" }}>
      <div className="disambig-header">
        <span className="disambig-badge">🔍 Disambiguation</span>
        <h2 className="disambig-title">{result.title}</h2>
        <p className="disambig-subtitle">
          The topic you searched for is ambiguous. Please select one of the specific articles below:
        </p>
      </div>

      <div className="disambig-filter-wrapper">
        <input
          type="text"
          className="disambig-filter-input"
          placeholder="🔍 Filter options (e.g. cricketer, road, film)..."
          value={filterText}
          onChange={e => setFilterText(e.target.value)}
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
              whileHover={{ scale: 1.015, backgroundColor: "rgba(99,102,241,0.08)", borderColor: "rgba(99,102,241,0.4)" }}
              whileTap={{ scale: 0.995 }}
            >
              <h3 className="disambig-option-title">{opt.title}</h3>
              <p className="disambig-option-desc">{opt.description}</p>
            </motion.div>
          ))
        ) : (
          <div className="disambig-no-results">
            No matching options found. Try checking your spelling or search filter.
          </div>
        )}
      </div>
    </motion.div>
  );
}

/* ── Main App ────────────────────────────────────────────────────────────── */

/* ── Main App ────────────────────────────────────────────────────────────── */
export default function App() {
  /* existing state */
  const [query,     setQuery]     = useState("");
  const [result,    setResult]    = useState(null);
  const [loading,   setLoading]   = useState(false);

  const [aiQuestion,  setAiQuestion]  = useState("");
  const [aiAnswer,    setAiAnswer]    = useState("");
  const [sources,     setSources]     = useState([]);
  const [askingAI,    setAskingAI]    = useState(false);
  const [totalChunks,     setTotalChunks]     = useState(0);
  const [retrievedChunks, setRetrievedChunks] = useState(0);
  const [cacheHit,        setCacheHit]        = useState(false);
  const [responseTime,    setResponseTime]    = useState("");

  const [history, setHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; }
    catch { return []; }
  });

  /* NEW state */
  const [images,           setImages]           = useState([]);
  const [tables,           setTables]           = useState([]);
  const [linkDescriptions, setLinkDescriptions] = useState({});
  const [relatedImage,     setRelatedImage]     = useState(null);
  const [tablesOpen,       setTablesOpen]       = useState(false);

  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  }, [history]);

  const addToHistory = useCallback((term) => {
    if (!term.trim()) return;
    setHistory(prev => {
      const filtered = prev.filter(h => h.toLowerCase() !== term.toLowerCase());
      return [term, ...filtered].slice(0, MAX_HISTORY);
    });
  }, []);

  const clearHistory = () => setHistory([]);

  /* ── Search ─────────────────────────────────────────────────────────────── */
  const doSearch = useCallback(async (searchQuery) => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    setResult(null);
    setAiAnswer(""); setSources([]); setAiQuestion("");
    setTotalChunks(0); setRetrievedChunks(0); setCacheHit(false); setResponseTime("");
    setImages([]); setTables([]); setLinkDescriptions({});
    setRelatedImage(null); setTablesOpen(false);

    try {
      const res  = await fetch("http://127.0.0.1:8001/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery }),
      });
      const data = await res.json();
      setResult(data);
      if (!data.error) {
        addToHistory(data.corrected_query || searchQuery);
        setImages(data.images            || []);
        setTables(data.tables            || []);
        setLinkDescriptions(data.link_descriptions || {});
      }
    } catch {
      setResult({ error: "Failed to connect to backend. Is the server running?" });
    }
    setLoading(false);
  }, [addToHistory]);

  const handleSearch      = () => doSearch(query);
  const handleHistoryClick = (term) => { setQuery(term); doSearch(term); };

  /* ── Ask AI ──────────────────────────────────────────────────────────────── */
  const handleAskAI = async () => {
    if (!aiQuestion.trim()) return;
    setAskingAI(true);
    setAiAnswer(""); setSources([]);
    setTotalChunks(0); setRetrievedChunks(0); setCacheHit(false); setResponseTime("");
    setRelatedImage(null);

    try {
      const res  = await fetch("http://127.0.0.1:8001/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          article:  result.full_content || result.summary || "",
          question: aiQuestion,
          title:    result.title || "",
          images,                   // pass all page images for semantic matching
        }),
      });
      const data = await res.json();
      setAiAnswer(data.answer         || "No answer returned.");
      setSources(data.sources         || []);
      setTotalChunks(data.total_chunks       || 0);
      setRetrievedChunks(data.retrieved_chunks || 0);
      setCacheHit(!!data.cache_hit);
      setResponseTime(data.time       || "");
      setRelatedImage(data.related_image || null);
    } catch {
      setAiAnswer("Failed to connect to the AI service.");
    }
    setAskingAI(false);
  };

  /* ── Render ──────────────────────────────────────────────────────────────── */
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
        <motion.div className="header" initial="hidden" animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.12 } } }}>
          <motion.div className="header-badge" variants={fadeUp}>⚡ Powered by RAG + Llama 3.1</motion.div>
          <motion.h1 variants={fadeUp}>AI Wikipedia Search</motion.h1>
          <motion.p className="header-subtitle" variants={fadeUp}>
            Ask questions about any topic — powered by retrieval-augmented generation
          </motion.p>
        </motion.div>

        {/* ── Search bar ── */}
        <motion.div className="search-container"
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}>
          <input
            id="search-input" className="search-input" type="text"
            placeholder="Search any topic  (e.g. Virat Kohli, Black holes, C++)"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSearch()}
          />
          <motion.button id="search-button" className="search-button" onClick={handleSearch}
            whileHover={{ scale: 1.04, translateY: -2 }} whileTap={{ scale: 0.96 }}
            transition={{ type: "spring", stiffness: 350, damping: 20 }}>
            Search →
          </motion.button>
        </motion.div>

        {/* ── History ── */}
        <AnimatePresence>
          {history.length > 0 && (
            <motion.div className="history-row"
              initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.3 }}>
              <span className="history-label">🕒 Recent searches</span>
              {history.map((term, i) => (
                <motion.button key={term} className="history-chip"
                  onClick={() => handleHistoryClick(term)}
                  title={`Search "${term}" (cached)`}
                  custom={i} variants={slideRight} initial="hidden" animate="visible" exit="exit"
                  whileHover={{ scale: 1.07, y: -2 }} whileTap={{ scale: 0.95 }}>
                  {term}
                </motion.button>
              ))}
              <motion.button className="history-clear" onClick={clearHistory}
                whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
                Clear
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Loading ── */}
        <AnimatePresence>
          {loading && (
            <motion.div className="loading-wrapper"
              initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.85 }} transition={{ duration: 0.3 }}>
              <div className="spinner" />
              <motion.span animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}>
                Searching Wikipedia…
              </motion.span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Error ── */}
        <AnimatePresence>
          {result?.error && (
            result.error.includes("No Wikipedia article found") ? (
              <motion.div className="not-found-card" key="not-found"
                variants={scaleIn} initial="hidden" animate="visible" exit="exit">
                <motion.div className="not-found-icon"
                  animate={{ rotate: [0, -10, 10, -10, 0] }}
                  transition={{ delay: 0.3, duration: 0.6 }}>🔍</motion.div>
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
              <motion.div className="error-message" key="error"
                variants={fadeUp} initial="hidden" animate="visible" exit="exit">
                ⚠️ {result.error}
              </motion.div>
            )
          )}
        </AnimatePresence>

        {/* ── Results ── */}
        <AnimatePresence>
          {result && !result.error && (
            <motion.div key="results" initial="hidden" animate="visible" exit="exit"
              variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.1 } } }}>

              {/* Spell-correction banner */}
              {result.corrected_query && (
                <motion.div className="correction-banner" variants={fadeUp}>
                  <span className="correction-icon">🔤</span>
                  <span>Showing results for <strong>{result.corrected_query}</strong></span>
                  <span className="correction-original">&nbsp;(you searched: "{result.original_query}")</span>
                </motion.div>
              )}

              {result.is_disambiguation ? (
                /* ── Disambiguation View ── */
                <DisambiguationView result={result} doSearch={doSearch} setQuery={setQuery} />
              ) : (
                /* ── Standard Article card ── */
                <motion.div className="result-card" variants={fadeUp}
                  whileHover={{ y: -4, boxShadow: "0 16px 48px rgba(0,0,0,0.6), 0 0 40px rgba(99,102,241,0.18)" }}
                  transition={{ type: "spring", stiffness: 300, damping: 24 }}>
                  {result.image && (
                    <motion.div className="article-image-wrap"
                      initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
                      <motion.img src={result.image} alt={result.title}
                        className="article-image" whileHover={{ scale: 1.04 }} transition={{ duration: 0.35 }} />
                    </motion.div>
                  )}
                  <div className="content">
                    <motion.div className="article-meta"
                      initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.25 }}>
                      <span className="meta-tag">📖 Wikipedia</span>
                    </motion.div>
                    <motion.h2 className="result-title"
                      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, duration: 0.4 }}>
                      {result.title}
                    </motion.h2>
                    <motion.p className="result-summary"
                      initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4, duration: 0.5 }}>
                      {result.summary_segments && result.summary_segments.length > 0 ? (
                        result.summary_segments.map((seg, idx) => {
                          if (seg.link && linkDescriptions[seg.link]) {
                            const info = linkDescriptions[seg.link];
                            return (
                              <span key={idx} className="inline-wiki-link-wrapper">
                                <button
                                  className="inline-wiki-link"
                                  onClick={() => {
                                    setQuery(seg.link);
                                    doSearch(seg.link);
                                  }}
                                >
                                  {seg.text}
                                </button>
                                <span className="wiki-hover-card">
                                  {info.thumbnail && (
                                    <img
                                      src={info.thumbnail}
                                      alt={seg.link}
                                      className="wiki-hover-card-img"
                                      loading="lazy"
                                    />
                                  )}
                                  <span className="wiki-hover-card-content">
                                    <span className="wiki-hover-card-title">{seg.link}</span>
                                    <span className="wiki-hover-card-desc">{info.description}</span>
                                  </span>
                                </span>
                              </span>
                            );
                          }
                          return <span key={idx}>{seg.text}</span>;
                        })
                      ) : (
                        result.summary
                      )}
                    </motion.p>
                    <motion.a href={result.url} target="_blank" rel="noreferrer" className="read-link"
                      initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 }}
                      whileHover={{ x: 5, scale: 1.03 }}>
                      Read Full Article →
                    </motion.a>
                  </div>
                </motion.div>
              )}

              {/* ── Image Gallery ── */}
              {images.length > 0 && (
                <motion.div className="image-gallery-section" variants={fadeUp}>
                  <div className="gallery-section-header">
                    <span>🖼️ Page Images</span>
                    <span className="gallery-count">{images.length} images</span>
                  </div>
                  <div className="image-gallery">
                    {images.map((img, i) => (
                      <motion.div key={i} className="gallery-item"
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: i * 0.04, duration: 0.35 }}
                        whileHover={{ scale: 1.04, y: -4 }}>
                        <div className="gallery-img-wrap">
                          <img src={img.url} alt={img.caption} loading="lazy" />
                        </div>
                        <div className="gallery-caption">{img.caption}</div>
                      </motion.div>
                    ))}
                  </div>
                </motion.div>
              )}

              {/* ── Tables section ── */}
              {tables.length > 0 && (
                <motion.div className="tables-section" variants={fadeUp}>
                  <button className="tables-header" onClick={() => setTablesOpen(o => !o)}>
                    <span>📊 Article Tables <span className="table-count">({tables.length})</span></span>
                    <motion.span
                      animate={{ rotate: tablesOpen ? 180 : 0 }}
                      transition={{ duration: 0.25 }}
                      className="accordion-chevron">▼</motion.span>
                  </button>
                  <AnimatePresence>
                    {tablesOpen && (
                      <motion.div className="tables-body"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}>
                        {tables.map((table, i) => (
                          <motion.div key={i} className="wiki-table-wrapper"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.08 }}>
                            {table.caption && (
                              <div className="table-caption">{table.caption}</div>
                            )}
                            <div className="table-scroll">
                              <table className="wiki-table">
                                {table.headers.some(h => h) && (
                                  <thead>
                                    <tr>{table.headers.map((h, j) => <th key={j}>{h}</th>)}</tr>
                                  </thead>
                                )}
                                <tbody>
                                  {table.rows.map((row, j) => (
                                    <tr key={j}>
                                      {row.map((cell, k) => <td key={k}>{cell}</td>)}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </motion.div>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              )}

              {/* ── Ask AI section ── */}
              <motion.div className="ai-section" variants={fadeUp}>
                <div className="ai-section-header">
                  <motion.div className="ai-icon"
                    animate={{ rotate: [0, 5, -5, 0] }}
                    transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
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
                  <input id="ai-input" className="ai-input" type="text"
                    placeholder="e.g. When was he born? What is the main cause?"
                    value={aiQuestion}
                    onChange={e => setAiQuestion(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && handleAskAI()} />
                  <motion.button id="ask-button" className="ask-button"
                    onClick={handleAskAI} disabled={askingAI}
                    whileHover={!askingAI ? { scale: 1.05, y: -2 } : {}}
                    whileTap={!askingAI ? { scale: 0.97 } : {}}
                    transition={{ type: "spring", stiffness: 350, damping: 20 }}>
                    {askingAI ? "Thinking…" : "Ask AI"}
                  </motion.button>
                </div>

                {/* Thinking indicator */}
                <AnimatePresence>
                  {askingAI && (
                    <motion.div className="ai-thinking"
                      initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.3 }}>
                      <div className="thinking-dots"><span /><span /><span /></div>
                      AI is reading the article…
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Answer + Related Image + Sources */}
                <AnimatePresence>
                  {aiAnswer && (
                    <motion.div className="ai-answer" key="ai-answer"
                      initial={{ opacity: 0, y: 20, scale: 0.97 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -10 }}
                      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}>

                      {/* Stats panel */}
                      <motion.div className="stats-panel" initial="hidden" animate="visible"
                        variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.08 } } }}>
                        {[
                          { isNum: true,  val: totalChunks,     label: "Chunks Created" },
                          { isNum: true,  val: retrievedChunks, label: "Retrieved" },
                          { isNum: false, badge: true,          label: "Cache Status" },
                          { isNum: false, time:  true,          label: "Response Time" },
                        ].map((item, i) => (
                          <motion.div key={i} className="stats-card" custom={i} variants={scaleIn}
                            whileHover={{ scale: 1.05, y: -2 }}>
                            {item.isNum  && <span className="stats-val"><AnimatedNumber value={item.val} /></span>}
                            {item.badge  && <span className={`badge ${cacheHit ? "cache-hit" : "cache-miss"}`}>{cacheHit ? "🟢 Cache HIT" : "🔵 Fresh Gen"}</span>}
                            {item.time   && <span className="stats-val time-val">⚡ {responseTime}</span>}
                            <span className="stats-lbl">{item.label}</span>
                          </motion.div>
                        ))}
                      </motion.div>

                      {/* Related Image (AI-matched) */}
                      <AnimatePresence>
                        {relatedImage && (
                          <motion.div className="related-image-card"
                            initial={{ opacity: 0, scale: 0.92, y: 12 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.9 }}
                            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}>
                            <div className="related-img-label">
                              <span className="related-img-icon">📸</span>
                              Related Image
                              <span className="related-img-score">
                                {Math.round((relatedImage.match_score || 0) * 100)}% match
                              </span>
                            </div>
                            <img src={relatedImage.url} alt={relatedImage.caption} className="related-img" />
                            <div className="related-img-caption">{relatedImage.caption}</div>
                          </motion.div>
                        )}
                      </AnimatePresence>

                      {/* Answer text */}
                      <div className="answer-header">
                        <motion.span className="answer-label"
                          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}>
                          ✦ AI Answer
                        </motion.span>
                      </div>
                      <motion.div className="answer-body"
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                        transition={{ delay: 0.25, duration: 0.5 }}>
                        {aiAnswer}
                      </motion.div>

                      {/* Sources */}
                      {sources.length > 0 && (
                        <>
                          <div className="sources-header">
                            <span className="sources-label">Sources Used</span>
                            <span className="sources-count">{sources.length} chunk{sources.length > 1 ? "s" : ""}</span>
                          </div>
                          <motion.div className="sources-list" initial="hidden" animate="visible"
                            variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.07 } } }}>
                            {sources.map((src, i) => (
                              <motion.div key={i} className="source-card" custom={i} variants={slideRight}
                                whileHover={{ x: 4, backgroundColor: "rgba(255,255,255,0.05)" }}>
                                <div className="source-card-header">
                                  <span className="source-index">Source {i + 1}</span>
                                  <motion.span className="source-score"
                                    initial={{ opacity: 0, scale: 0.8 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    transition={{ delay: 0.15 + i * 0.07 }}>
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