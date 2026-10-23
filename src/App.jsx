import { useState } from "react";
import "./App.css";

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");

  function sendMessage(e) {
    e.preventDefault();

    if (!input.trim()) return;

    setMessages([
      ...messages,
      { role: "user", text: input }
    ]);

    setInput("");
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <h2>✦ Memory AI</h2>

        <button
          className="new-chat"
          onClick={() => setMessages([])}
        >
          + New conversation
        </button>

        <p className="sidebar-label">YOUR CHAT</p>
        <p className="chat-item">◷ Current conversation</p>
      </aside>

      <main className="chat">
        <header className="header">
          <div className="avatar">✦</div>
          <div>
            <h3>AI Assistant</h3>
            <p>Your personal AI companion</p>
          </div>
          <span className="online">● Online</span>
        </header>

        <section className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <div className="welcome-icon">✦</div>
              <h1>What can I help you with?</h1>
              <p>Start a conversation with your AI assistant.</p>
            </div>
          )}

          {messages.map((message, index) => (
            <div className="user-message" key={index}>
              {message.text}
            </div>
          ))}
        </section>

        <form className="composer" onSubmit={sendMessage}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Message your AI assistant..."
          />
          <button type="submit">Send ↑</button>
        </form>
      </main>
    </div>
  );
}

export default App;