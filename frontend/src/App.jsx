import { useState } from "react";

function App() {
  const [query, setQuery] = useState("");

  const searchWikipedia = async () => {
    const response = await fetch("http://127.0.0.1:8000/search", {
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
  };

  return (
    <div
      style={{
        padding: "40px",
        fontFamily: "Arial",
      }}
    >
      <h1>AI Wikipedia Search</h1>

      <input
        type="text"
        placeholder="Enter a topic..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{
          padding: "10px",
          width: "300px",
          marginRight: "10px",
        }}
      />

      <button onClick={searchWikipedia}>
        Search
      </button>
    </div>
  );
}

export default App;