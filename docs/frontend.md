# 🎨 Frontend Documentation

This document explains the React frontend — its architecture, component structure, state management, UI design system, and how it communicates with the backend.

---

## Table of Contents

- [Technology Choices](#technology-choices)
- [File Structure](#file-structure)
- [App.jsx — Component Architecture](#appjsx--component-architecture)
- [State Management](#state-management)
- [API Integration](#api-integration)
- [Search History](#search-history)
- [UI Component Breakdown](#ui-component-breakdown)
- [Design System (App.css)](#design-system-appcss)
- [Animations and Micro-interactions](#animations-and-micro-interactions)
- [Responsive Design](#responsive-design)
- [Performance Considerations](#performance-considerations)

---

## Technology Choices

| Technology | Why Chosen |
|---|---|
| **React 19** | Industry-standard component library; excellent state management with hooks |
| **Vite 8** | Extremely fast dev server (HMR), modern ESM bundling |
| **Vanilla CSS** | Maximum flexibility; no framework overhead; 930 lines of carefully crafted CSS |
| **No Redux / Zustand** | The app's state is simple enough for React's built-in `useState` |
| **No React Router** | Single-page application with one view; routing is unnecessary overhead |
| **localStorage** | Simple, no-setup persistence for search history |

---

## File Structure

```
frontend/src/
├── main.jsx       ← React DOM entry point
├── App.jsx        ← Single component containing all logic and UI (356 lines)
├── App.css        ← Complete design system + component styles (930 lines)
└── index.css      ← Global reset (minimal)

frontend/
├── index.html     ← HTML shell with <div id="root">
├── package.json   ← Dependencies and scripts
└── vite.config.js ← Vite configuration (React plugin)
```

---

## App.jsx — Component Architecture

The entire application is a **single functional component** (`App`). This design choice keeps the codebase simple and avoids prop-drilling complexity for an application of this scope.

### Component Render Tree

```
App (root)
│
├── <div.bg-glows>          ← Decorative animated background circles
│   ├── glow-circle glow-1
│   ├── glow-circle glow-2
│   └── glow-circle glow-3
│
└── <div.container>         ← Main content wrapper (max-width 860px)
    │
    ├── <div.header>        ← Title, badge, subtitle
    │
    ├── <div.search-container>  ← Search input + button
    │
    ├── <div.history-row>   ← Clickable search history chips (conditional)
    │
    ├── <div.loading-wrapper>   ← Spinner (conditional, during search)
    │
    ├── <div.not-found-card>    ← 404 error card (conditional)
    ├── <div.error-message>     ← Generic error (conditional)
    │
    └── [Result Section]    ← Conditional: shown only after successful search
        │
        ├── <div.correction-banner>  ← Typo correction notice (conditional)
        │
        ├── <div.result-card>        ← Wikipedia article display
        │   ├── <img.article-image>  ← Article thumbnail (conditional)
        │   └── <div.content>
        │       ├── <span.meta-tag>  ← "📖 Wikipedia" badge
        │       ├── <h2>             ← Article title
        │       ├── <p>              ← Article summary
        │       └── <a.read-link>   ← "Read Full Article →"
        │
        └── <div.ai-section>         ← Ask AI panel
            ├── AI section header (icon + title)
            ├── <div.ai-input-row>   ← Question input + Ask button
            ├── <div.ai-thinking>    ← Animated dots (conditional)
            └── <div.ai-answer>      ← Answer display (conditional)
                ├── <div.stats-panel>    ← 4 metric cards
                ├── <div.answer-header>  ← "✦ AI Answer" label
                ├── <div.answer-body>    ← Answer text
                └── <div.sources-list>  ← Source chunk cards
```

---

## State Management

The app uses **7 state variables** managed with React's `useState` hook:

### Search State

```jsx
const [query, setQuery] = useState("");       // Current search input value
const [result, setResult] = useState(null);   // Wikipedia API response
const [loading, setLoading] = useState(false); // Search loading indicator
```

### Ask AI State

```jsx
const [aiQuestion, setAiQuestion] = useState("");  // Current question input
const [aiAnswer, setAiAnswer] = useState("");       // LLM answer text
const [sources, setSources] = useState([]);         // Retrieved chunks array
const [askingAI, setAskingAI] = useState(false);   // AI loading indicator
```

### RAG Statistics State

```jsx
const [totalChunks, setTotalChunks] = useState(0);     // Total article chunks
const [retrievedChunks, setRetrievedChunks] = useState(0); // Chunks sent to LLM
const [cacheHit, setCacheHit] = useState(false);       // Whether answer was cached
const [responseTime, setResponseTime] = useState("");   // e.g. "2.34 s"
```

### Search History State

```jsx
const [history, setHistory] = useState(() => {
    try {
        return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
    } catch {
        return [];
    }
});
```

This uses a **lazy initializer** (function form of `useState`) to read from `localStorage` only once on mount, avoiding performance issues from reading storage on every render.

### State Reset on New Search

Every time a new search begins, all dependent state is reset:

```jsx
setLoading(true);
setResult(null);     // Clear previous article
setAiAnswer("");     // Clear previous AI answer
setSources([]);      // Clear previous sources
setAiQuestion("");   // Clear previous question
setTotalChunks(0);
setRetrievedChunks(0);
setCacheHit(false);
setResponseTime("");
```

This prevents stale state from a previous search appearing while a new search loads.

---

## API Integration

### `doSearch` — Wikipedia Search

```jsx
const doSearch = useCallback(async (searchQuery) => {
    // ... reset state ...
    const res = await fetch("http://127.0.0.1:8001/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery }),
    });
    const data = await res.json();
    setResult(data);
    if (!data.error) {
        addToHistory(data.corrected_query || searchQuery);
    }
}, [addToHistory]);
```

**`useCallback`** is used here because `doSearch` is passed as a prop to child elements (history chips). Without `useCallback`, a new function reference would be created on every render, causing unnecessary re-renders of history chips.

### `handleAskAI` — RAG Question

```jsx
const handleAskAI = async () => {
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
};
```

**Priority for article content:** `full_content` is sent if available (for better RAG quality). The `summary` is a fallback for cases where the full article fetch failed. The `title` is sent as the FAISS index key — the backend uses it to load or save the persisted FAISS index.

### Error Handling

```jsx
try {
    const res = await fetch(...);
    const data = await res.json();
    // ...
} catch {
    setResult({ error: "Failed to connect to backend. Is the server running?" });
}
```

The `catch` block handles network failures (backend not running) and JSON parse errors. The frontend never crashes — it always shows a user-friendly error message.

---

## Search History

### Persistence

```jsx
const HISTORY_KEY = "wiki_search_history";
const MAX_HISTORY = 10;

// Read from localStorage on mount
const [history, setHistory] = useState(() => {
    return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
});

// Write to localStorage on every change
useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
}, [history]);
```

`useEffect` with `[history]` dependency ensures the storage write only happens when history actually changes, not on every render.

### Deduplication

```jsx
const addToHistory = useCallback((term) => {
    setHistory((prev) => {
        const filtered = prev.filter(
            (h) => h.toLowerCase() !== term.toLowerCase()
        );
        return [term, ...filtered].slice(0, MAX_HISTORY);
    });
}, []);
```

If `"Virat Kohli"` is already in history and you search it again, the old entry is removed and it moves to the top. History is capped at 10 entries.

### Replay on Click

```jsx
const handleHistoryClick = (term) => {
    setQuery(term);    // Update the search input
    doSearch(term);    // Trigger the search
};
```

Clicking a history chip both fills the search input *and* immediately runs the search, so the user gets instant cached results.

---

## UI Component Breakdown

### Header

```jsx
<div className="header">
    <div className="header-badge">⚡ Powered by RAG + Llama 3.1</div>
    <h1>AI Wikipedia Search</h1>
    <p className="header-subtitle">
        Ask questions about any topic — powered by retrieval-augmented generation
    </p>
</div>
```

The badge uses a gradient border and uppercase tracking for a premium tech feel.

### Wikipedia Article Card

Displays after a successful search. Key features:
- **Image**: `object-fit: contain` so images are never cropped (some Wikipedia images are tall/wide)
- **Correction banner**: Yellow warning bar if the query was auto-corrected
- **"Read Full Article →"** link: Opens Wikipedia in a new tab

### Stats Panel (RAG Transparency)

```jsx
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
```

This panel makes the RAG pipeline **transparent to the user** — they can see exactly how many chunks were created, how many were used, and whether the answer came from cache.

### Source Cards

```jsx
{sources.map((src, i) => (
    <div key={i} className="source-card">
        <div className="source-card-header">
            <span className="source-index">Source {i + 1}</span>
            <span className="source-score">
                Similarity: {Math.round(src.score * 100)}%
            </span>
        </div>
        <div className="source-text">{src.text}</div>
    </div>
))}
```

Each source card shows the exact Wikipedia text chunk that was used to generate the answer, plus its cosine similarity score as a percentage. This enables **full citation transparency** — the user can verify the answer against the source.

---

## Design System (App.css)

The CSS uses **CSS custom properties** (variables) for consistent theming:

```css
:root {
    --bg-base:      #060910;   /* Deep dark background */
    --bg-surface:   #0d1117;
    --bg-card:      rgba(255,255,255,0.04);  /* Glassmorphism */
    --border:       rgba(255,255,255,0.08);
    --border-focus: rgba(99,179,237,0.6);

    --text-primary: #f0f6ff;
    --text-muted:   #8b9ab3;

    --accent-blue:   #3b82f6;
    --accent-violet: #8b5cf6;
    --accent-pink:   #ec4899;

    --grad-title: linear-gradient(120deg, #38bdf8 0%, #818cf8 50%, #ec4899 100%);
    --grad-btn:   linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
}
```

### Glassmorphism

Cards use a semi-transparent background with `backdrop-filter: blur()`:

```css
.result-card {
    background: rgba(255, 255, 255, 0.04);  /* Very slight transparency */
    border: 1px solid rgba(255, 255, 255, 0.08);
    backdrop-filter: blur(12px);             /* Frosted glass effect */
}
```

### Typography

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

h1 {
    font-size: clamp(36px, 6vw, 60px);  /* Fluid typography */
    font-weight: 800;
    background: var(--grad-title);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;  /* Gradient text */
}
```

---

## Animations and Micro-interactions

### Page Entrance (`fadeUp`)

All cards and sections animate in from below on appearance:

```css
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(18px); }
    to   { opacity: 1; transform: translateY(0); }
}

.result-card   { animation: fadeUp 0.4s ease; }
.ai-section    { animation: fadeUp 0.5s ease 0.1s both; }
.ai-answer     { animation: fadeUp 0.4s ease; }
```

The `0.1s` delay on `.ai-section` creates a stagger effect — article card appears first, then the AI section slides up.

### Thinking Dots (AI Loading)

```css
.thinking-dots span {
    animation: bounce 1.2s infinite;
}
.thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
    0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
    40%           { transform: translateY(-6px); opacity: 1; }
}
```

Three dots bounce sequentially — a universally understood "AI is thinking" indicator.

### Button Hover States

```css
.search-button:hover {
    transform: translateY(-2px);         /* Lift effect */
    box-shadow: 0 8px 30px rgba(59,130,246,0.5);  /* Glow */
}

.read-link:hover {
    transform: translateX(3px);          /* Slide right → direction hint */
}
```

Each button type has a hover animation appropriate to its function — lift for primary actions, slide for navigation links.

---

## Responsive Design

```css
@media (max-width: 640px) {
    .container { padding: 40px 0 60px; }
    h1 { font-size: 32px; }
    .search-container { flex-direction: column; }  /* Stack input + button */
    .ai-input-row { flex-direction: column; }       /* Stack input + button */
    .content, .ai-section { padding: 22px 20px; }  /* Reduce padding */
    .result-title { font-size: 22px; }
    .stats-panel { grid-template-columns: repeat(2, 1fr); }  /* 2x2 grid */
}
```

On mobile, the search bar and AI input stack vertically so the button is full-width and easy to tap. The stats panel switches from a 4-column to a 2×2 grid.

---

## Performance Considerations

| Optimization | Implementation |
|---|---|
| **`useCallback` for `doSearch`** | Prevents recreation of the function on every render |
| **`useCallback` for `addToHistory`** | Stable reference for history chip event handlers |
| **Lazy `useState` initializer** | `localStorage` is read only once on mount |
| **Conditional rendering** | Loading spinner, results, and error states are only rendered when needed |
| **Model loaded once** | The SentenceTransformer model is loaded at backend startup, not per-request |
| **FAISS index cached** | Embeddings are computed once per article and reloaded from disk |
| **CSS animations** | All animations use `transform` and `opacity` — GPU-accelerated, no layout reflow |
| **Inter font via CDN** | Google Fonts CDN is globally cached; no bundle size impact |
