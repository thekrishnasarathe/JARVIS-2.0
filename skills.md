# Technology Stack & Skills Demonstrated

## Core Architecture
* **Python 3.12+**: The backbone of the entire ecosystem.
* **Concurrency**: Advanced utilization of `threading.Thread` and `asyncio` to manage parallel subagents and hardware daemons without blocking the main event loop.
* **Event-Driven Microservices**: Implementation of an asynchronous `event_bus` to seamlessly decouple the frontend UI from the backend business logic.

## AI & Machine Learning
* **Ollama**: Local, secure LLM inference for the core routing and conversational memory.
* **LLM Tool Calling**: Leveraging structured JSON schemas to allow the LLM to autonomously invoke Python functions (e.g., `spawn_subagent`, `get_weather`).
* **Computer Vision**: Utilizing OpenCV and facial recognition libraries for biometric security lockdowns.
* **Speech-To-Text (STT)**: Integration of `SpeechRecognition` and `pvporcupine` for a low-latency, offline wake-word and transcription pipeline.

## Native GUI & 3D Rendering
* **PyQt6**: Engineered a frameless, holographic dashboard featuring custom QFrames, QScrollAreas, and dynamic styling via `pyqtdarktheme`.
* **PyVista**: Rendered a responsive 3D VTK core using `ParametricTorus` and `Sphere` meshes, actively manipulating opacity, color arrays, and rotation vectors based on real-time hardware telemetry.

## System Operations
* **psutil**: Real-time cross-platform hardware telemetry (CPU, RAM) polling.
* **pytest**: Comprehensive automated unit testing with extensive object mocking to run GUI components headlessly in CI/CD pipelines (Xvfb).
* **API Interoperability**: Utilization of `requests`, `pywhatkit`, and `wikipedia` to connect the local AI OS to global datasets.
