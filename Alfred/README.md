🎩 Alfred — Your Local AI Butler
A private, local AI chat assistant with a butler personality, long-term memory, and document chat (RAG). Runs entirely on your machine — no API keys, no cloud, no data leaving your computer.


✨ Features
🎩 Butler persona — witty, loyal, calls you "sir"
🎲 Random greetings — a fresh one every page load
🧠 Persistent memory — tell it your name once, it remembers across restarts (memory.json)
📚 Chat with documents (RAG) — upload PDF/TXT/MD, ask questions, get cited sources
🎚️ Quality presets — low / medium / high (temperature + token limits)
🎤 Voice input — built-in Web Speech API
📊 Live token stats — input, thread, and context-cap tracking
🛡️ Robust error handling — JSON errors, never a mystery 500
🛠️ Tech Stack
Layer	Tech
Frontend	HTML, CSS, Vanilla JS
Backend	Flask (Python)
LLM	Ollama (llama3.2:3b)
Embeddings	Ollama (nomic-embed-text)
Vector store	ChromaDB
Memory	JSON file (persistent)
