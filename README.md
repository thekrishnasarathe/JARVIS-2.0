<div align="center">
  <h1>🌌 JARVIS 2.0 🌌</h1>
  <p><strong>Advanced Multi-Modal Desktop & Cloud AI Assistant</strong></p>
  <p><i>Autonomous Agent Swarms • Spatial Memory Theater • Native 3D GUI • Biometric Security • Web HUD Gateway</i></p>

  [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
  [![PyQt6](https://img.shields.io/badge/PyQt-6.5%2B-brightgreen.svg)](https://riverbankcomputing.com/software/pyqt/)
  [![Tests: 54 Passed](https://img.shields.io/badge/Tests-54%20Passed-success.svg)](tests/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
</div>

---

## 🌐 Live Deployments & Demo

| Service | Component | Status | URL |
| :--- | :--- | :--- | :--- |
| **Vercel** | Iron Man HUD Web Frontend | [![Vercel](https://img.shields.io/badge/Vercel-Deployed-black?logo=vercel)](https://jarvis-20-web.vercel.app/?api=https://jarvis-2-0-dv4v.onrender.com) | [jarvis-20-web.vercel.app](https://jarvis-20-web.vercel.app/?api=https://jarvis-2-0-dv4v.onrender.com) |
| **Render** | FastAPI Backend Gateway | [![Render](https://img.shields.io/badge/Render-Online-46E3B7?logo=render)](https://jarvis-2-0-dv4v.onrender.com/docs) | [jarvis-2-0-dv4v.onrender.com](https://jarvis-2-0-dv4v.onrender.com) |
| **API Health** | Gateway Probe | `GET /health` | [jarvis-2-0-dv4v.onrender.com/health](https://jarvis-2-0-dv4v.onrender.com/health) |

---

## 🌟 Overview
**JARVIS 2.0** is a next-generation AI orchestrator that goes beyond a standard chat interface. It leverages a fully decoupled, asynchronous event-driven architecture combining local LLM routing with hardware sensor integration, background subagent swarms, an embedded 3D VTK visualization, and a cloud-ready FastAPI REST gateway.

Whether you're executing complex research tasks, monitoring system telemetry, or navigating your past conversations in 3D space, JARVIS 2.0 brings an Iron Man-level assistant experience directly to your desktop and browser.

---

## ✨ Flagship Features

### 🧠 Core LLM Router & Swarm Intelligence
- **Intelligent Routing:** Commands are intercepted and routed to optimized local/remote Python skill modules. If no exact match is found, queries elegantly fall back to the primary LLM (e.g., Groq/Llama3).
- **Agent Swarming:** JARVIS can spawn concurrent, non-blocking subagents (via `swarm.py`) using Tool Calling. Background workers research, scrape, or compute asynchronously, reporting back when missions are complete.

### 🎭 Spatial Memory Theater
- **Physical Memory Graph:** Your conversation history is plotted as gravitational nodes in 3D space using a custom force-directed physics engine.
- **Semantic Binding:** Nodes are bound using TF-IDF cosine similarity. Memories with related concepts attract each other, forming organic clusters over time.
- **Persistence:** The spatial arrangement is saved directly to a SQLite database across sessions.

### 🖥️ Dual Interfaces: Native 3D GUI & Web HUD
- **PyQt6 + PyVista Core:** Blends a responsive PyQt6 dashboard with an embedded VTK 3D visualization window.
- **Web HUD Gateway (`web/` & `app/`):** A cinematic Stark Industries Iron Man HUD with live telemetry, Arc Reactor voice recognition, sound synthesis, and full mobile/desktop responsiveness.

### 🛡️ Hardware & Biometric Security
- **Face Detection:** Background daemon uses OpenCV to monitor the webcam. If an unauthorized face is detected, the system locks the workstation.
- **Wake Word Engine:** Dedicated background thread listening for personalized activation phrases.
- **Battery & System Daemons:** Proactive monitors alert you when battery dips below critical thresholds.

### 🔌 Zero-Coupling Plugin System
- **Drop-in Extensibility:** Add new features simply by dropping a Python file into `plugins/`. The singleton `PluginRegistry` handles dynamic loading at runtime.

---

## 🏗️ Repository Architecture

```
JARVIS 2.0/
├── app/                  # FastAPI Web & REST API Gateway
│   ├── __init__.py
│   └── main.py           # Endpoints: /health, /api/command, /api/status, /api/memory
├── backend/              # Core Intelligence & Modules
│   ├── background/       # Daemon threads (battery, face security, wake-word)
│   ├── core/             # Central router, LLM fallback, STT, TTS, swarm
│   └── modules/          # Skill handlers, system tools, memory persistence
├── frontend/             # Desktop Native UI (PyQt6 + PyVista)
│   ├── main_window.py    # Primary Qt application controller
│   ├── memory_theater.py # 3D VTK render interactor
│   ├── threads.py        # Qt event loop workers
│   └── widgets.py        # Custom Iron Man HUD widgets
├── web/                  # Cloud-Deployable Web HUD Frontend
│   ├── index.html        # Futuristic Stark Industries HUD
│   ├── style.css         # Amber/Orange neon aesthetic
│   └── app.js            # Reactive Web Audio & Command client
├── plugins/              # Hot-swappable community skills
├── shared/               # Event bus, schemas, config & logging
├── tests/                # 54 passing automated Pytest suites
├── render.yaml           # Render 1-click cloud deployment spec
├── Procfile              # Uvicorn production entrypoint
└── vercel.json           # Vercel SPA routing rules
```

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` to configure your keys:

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `GROQ_API_KEY` | Optional | `""` | Groq API key for ultra-fast Llama-3.1 inference |
| `GROQ_MODEL` | Optional | `llama-3.1-8b-instant` | Groq model identifier |
| `WEATHER_API_KEY` | Optional | `""` | OpenWeatherMap API key for live weather forecasts |
| `PORCUPINE_ACCESS_KEY` | Optional | `""` | Picovoice key for offline wake-word recognition |
| `FRONTEND_URL` | Optional | `*` | Allowed CORS frontend origins (comma-separated or `*`) |
| `PORT` | Optional | `8000` | Port for the FastAPI web server |
| `JARVIS_THEATER_MODE` | Optional | `false` | Set `true` to boot desktop UI in 3D Memory Theater mode |

---

## 🚀 Quickstart & Execution

### 1. Installation
```bash
# Clone the repository
git clone <your-repo-url>
cd "JARVIS 2.0"

# Create and activate a virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate

# macOS / Linux:
source .venv/bin/activate

# Install dependencies:
# For Cloud Web Gateway / REST API:
pip install -r requirements.txt

# For Full 3D Desktop UI & Sensors:
pip install -r requirements-desktop.txt
```

### 2. Run Modes

#### 🌐 Mode A: Web Server & Cloud API (Render / Local Web)
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000 in your browser to access the Iron Man Web HUD!
```

#### 🖥️ Mode B: Native 3D Desktop UI (PyQt6 + VTK)
```bash
python run.py
```

#### 🎭 Mode C: Spatial Memory Theater
```bash
python run.py --theater
```

#### 💻 Mode D: Terminal CLI
```bash
python run.py --cli
```

---

## 🧪 Automated Testing
Run the automated test suite verifying routing, telemetry, background daemons, and physics:
```bash
pytest tests/ -v
```
*Current test suite: **54 passed in 8.8s** (100% pass rate).*

---

## ☁️ Free-Tier Cloud Deployment ($0)

### Backend (Render Free Web Service)
1. Fork or push this repository to GitHub.
2. Sign in to [Render](https://render.com) and click **New + > Web Service**.
3. Connect your GitHub repository.
4. Render automatically detects `render.yaml`.
   - **Build Command:** `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add your environment variables (`GROQ_API_KEY`, `WEATHER_API_KEY`, etc.) in the dashboard.
6. Verify live deployment at `https://<your-service>.onrender.com/health`.

### Frontend (Vercel)
1. Sign in to [Vercel](https://vercel.com) and click **Add New > Project**.
2. Import your GitHub repository.
3. Set **Root Directory** to `web` (or leave at root with `vercel.json`).
4. Set **Framework Preset** to `Other`.
5. Deploy! Vercel will host the Iron Man HUD with sub-second global CDN response.
6. Point your web client to your live Render backend by appending `?api=https://<your-backend>.onrender.com` or setting `localStorage.setItem('JARVIS_API_URL', 'https://<your-backend>.onrender.com')`.

---

<div align="center">
  <i>Engineered with Python, FastAPI, PyQt6, PyVista, and the 5-Agent Ecosystem.</i>
</div>
