# JARVIS 2.0

JARVIS 2.0 is an advanced, multi-module desktop AI assistant featuring a fully Native 3D GUI, autonomous agent swarming capabilities, voice activation, and biometric security integration. 

## Project Architecture

The application is built on a highly modular, decoupled architecture driven by an asynchronous event bus:
- **Core LLM Router:** Acts as the brain, routing natural language commands to specific system utilities, or answering directly via local Ollama LLMs.
- **Agent Swarm:** Supports parallel background subagents dispatched by the core LLM via Tool Calling for concurrent research and heavy lifting.
- **Background Daemons:** Hardware listeners (e.g., face detection, battery monitoring, wake-word engines) run in separate threads, pushing standardized payloads (`JarvisEvent`) to the event bus.
- **Native 3D UI:** A highly responsive PyQt6 interface rendering a PyVista VTK 3D core that dynamically reacts to system telemetry, LLM processing, and security events.

## The 5-Agent Development Workflow
This project was autonomously engineered via a strictly bounded 5-Agent Ecosystem:
1. **Backend Agent:** Engineered the core Python logic, LLM fallback mechanisms, and hardware listener threads.
2. **Frontend Agent:** Designed the futuristic 3D GUI, telemetry sidebars, and reactive holographic chat interface.
3. **Integration Agent:** Orchestrated cross-boundary data flow, event bus bridging, and repo scaffolding.
4. **DevOps & SRE Agent:** Managed virtual environments, dependencies, and deployment execution loops.
5. **QA & Testing Agent:** Enforced code quality via automated `pytest` mock infrastructures.

## Repository Breakdown
* `/backend`: Contains the core routing logic (`router.py`), background daemon threads (`face_monitor.py`, `wake_word.py`), swarm managers (`swarm.py`), and API services.
* `/frontend`: Houses the Native PyVista + PyQt6 application (`native_ui.py`).
* `/shared`: Holds the async `event_bus`, system configurations, and cross-boundary `schemas.py`.
* `/tests`: Contains headless Xvfb CI/CD pipeline tests and automated mock implementations.

## How to Run
### Prerequisites
- Python 3.10+
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/JARVIS-2.0.git
cd JARVIS-2.0
```

### 2. Create and Activate the Virtual Environment
**On Windows:**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**On macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run JARVIS 2.0
Launch the unified orchestrator to start the background daemon services alongside the Native 3D UI:
```bash
python run.py
```

*Note: You can use `python run.py --cli` to launch the application in terminal mode (no GUI), or `python run.py --no-bg` to start the interface without background monitors.*
