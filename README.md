<!-- Animated Header -->
<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:1a1b27,100:161b22&height=200&section=header&text=XOYO%20Omega&fontSize=50&fontColor=58a6ff&animation=fadeIn&fontAlignY=35&desc=Autonomous%20AI%20Operating%20System&descSize=18&descColor=8b949e&descAlignY=55" />

<div align="center">

[![Python](https://img.shields.io/badge/Python_3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![License](https://img.shields.io/badge/License-MIT-444444?style=for-the-badge)](LICENSE)

<br/>

<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=500&size=18&duration=3000&pause=1000&color=58A6FF&center=true&vCenter=true&width=700&lines=27+Core+Microservices+%7C+Expandable+to+45%2B+with+GPU;8+LLM+Providers+%7C+Zero-Failure+Cascading+Fallback;Self-Healing+%7C+Constitutional+Safety+%7C+Hierarchical+Memory" alt="Typing SVG" />

</div>

---

## ▸ What is XOYO?

XOYO is not a chatbot — it is a **full-stack autonomous AI operating system** designed to run locally on commodity hardware. It orchestrates a constellation of specialized microservices into one cohesive agent:

<table>
  <tr>
    <td width="14%" align="center"><strong>Think</strong></td>
    <td>Multi-provider LLM routing across 8 providers (Groq, Cerebras, Mistral, NVIDIA NIM, OpenRouter, Cloudflare, SiliconFlow, Ollama) with zero-failure cascading fallback</td>
    <td><code>Lite</code></td>
  </tr>
  <tr>
    <td align="center"><strong>Remember</strong></td>
    <td>Hierarchical memory — episodic recall, semantic retrieval, personal context, automatic consolidation</td>
    <td><code>Lite</code></td>
  </tr>
  <tr>
    <td align="center"><strong>Reason</strong></td>
    <td>Active Inference, Constitutional AI safety, multi-agent debate for complex decisions</td>
    <td><code>Lite</code></td>
  </tr>
  <tr>
    <td align="center"><strong>Act</strong></td>
    <td>Desktop control, web browsing, Google integration, document generation, autonomous code writing</td>
    <td><code>Lite</code></td>
  </tr>
  <tr>
    <td align="center"><strong>Self-Heal</strong></td>
    <td>Watchdog daemon with crash recovery, stuck-task detection, metacognitive tracing</td>
    <td><code>Lite</code></td>
  </tr>
  <tr>
    <td align="center"><strong>Perceive</strong></td>
    <td>Computer vision (YOLO, Florence, DINO), screen awareness, wakeword detection</td>
    <td><code>GPU</code></td>
  </tr>
  <tr>
    <td align="center"><strong>Speak</strong></td>
    <td>Neural TTS with prosody control, Whisper STT, full voice pipeline</td>
    <td><code>GPU</code></td>
  </tr>
</table>

---

## ▸ Hardware Tiers

XOYO scales to your hardware. Services are organized into tiers so the system runs well on anything from an ultrabook to a workstation.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  LITE       8 GB RAM  · No GPU     27 services    Intelligence + Memory     │
├──────────────────────────────────────────────────────────────────────────────┤
│  STANDARD   16 GB RAM · No GPU    ~35 services    + Science + Research      │
├──────────────────────────────────────────────────────────────────────────────┤
│  FULL       32 GB+    · CUDA GPU   45+ services   + Vision + Voice + LLMs   │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Switch tiers:**
```bash
# In xoyo_daemon.py — toggle this line:
LITE_MODE = True   # Set to False to unlock Standard/Full tier services

# Or manually uncomment specific services in start_xoyo.sh
```

---

## ▸ Architecture

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#000000',
    'primaryTextColor': '#F8F8F2',
    'primaryBorderColor': '#333333',
    'lineColor': '#444444',
    'secondaryColor': '#0A0A0A',
    'tertiaryColor': '#111111'
  }
}}%%
graph TB
    classDef frontend fill:#0A0A0A,stroke:#0070F3,stroke-width:1.5px,color:#FFFFFF,rx:6,ry:6
    classDef core fill:#0A0A0A,stroke:#7928CA,stroke-width:1.5px,color:#FFFFFF,rx:6,ry:6
    classDef mem fill:#0A0A0A,stroke:#FF0080,stroke-width:1.5px,color:#FFFFFF,rx:6,ry:6
    classDef reason fill:#0A0A0A,stroke:#F5A623,stroke-width:1.5px,color:#FFFFFF,rx:6,ry:6
    classDef tool fill:#0A0A0A,stroke:#00DFD8,stroke-width:1.5px,color:#FFFFFF,rx:6,ry:6
    classDef watch fill:#0A0A0A,stroke:#FF4D4D,stroke-width:1.5px,color:#FFFFFF,rx:6,ry:6
    classDef gpu fill:#0A0A0A,stroke:#50E3C2,stroke-width:1.5px,stroke-dasharray: 4 4,color:#FFFFFF,rx:6,ry:6
    classDef db fill:#0A0A0A,stroke:#0070F3,stroke-width:1.5px,color:#FFFFFF

    subgraph User["Interface Layer"]
        A["Dashboard UI"]:::frontend
        B["WebSockets"]:::frontend
    end
    
    subgraph CoreSys["Core Orchestration"]
        C["Orchestrator (FastAPI)"]:::core
        D["LLM Router (8 APIs)"]:::core
        E["Parallel Workers"]:::core
    end
    
    subgraph MemorySys["Neural Memory Bank"]
        J[("Redis Cache")]:::db
        F["Memory Manager"]:::mem
        G["Semantic Search"]:::mem
        I["Consolidator"]:::mem
    end
    
    subgraph LogicSys["Cognitive Reasoning"]
        L["Active Inference"]:::reason
        N["Multi-Agent Debate"]:::reason
        O["Constitutional Safety"]:::reason
    end
    
    subgraph ActionSys["Execution Tools"]
        U["Desktop Control"]:::tool
        V["Web Agent"]:::tool
        W["Office Tools"]:::tool
    end
    
    subgraph MonitorSys["Health & Safety"]
        Z["Stuck Detector"]:::watch
        AB["Task Doctor"]:::watch
    end
    
    subgraph Perception["GPU Perception (Optional)"]
        direction LR
        Q["YOLO Vision"]:::gpu
        S["Whisper STT"]:::gpu
        T2["Neural TTS"]:::gpu
    end

    %% Routing
    A <-->|HTTP/REST| C
    B <-->|Real-time Events| C
    C ==>|Tasks| D
    C -->|Spawns| E
    
    %% Memory Access
    C -.->|Reads/Writes| F
    F <==> J
    G <==> J
    I -.->|Optimization| J
    
    %% Cognitive loop
    C ===>|Delegates| L
    L --> N
    L --> O
    
    %% Action loop
    C --->|Commands| U
    C --->|Commands| V
    C --->|Commands| W
    
    %% Diagnostics
    Z -.->|Monitors| C
    AB -.->|Heals| C
    
    %% Optional 
    C -.->|Vision Data| Q
    C -.->|Voice Cmds| S
    C -.->|Voice Output| T2
```

---

## ▸ Quick Start

### Prerequisites

- **Python 3.10+**
- **Redis** — inter-service communication and memory persistence
- **8 GB+ RAM** — Lite Mode runs 27 services comfortably
- **CUDA GPU** *(optional)* — only needed for Full Tier perception and voice

### Installation

```bash
git clone https://github.com/shashankrpatil077-ctrl/xoyo.git
cd xoyo

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your API keys (Groq, Cerebras, Mistral, etc.)
```

### Launch

```bash
./start_xoyo.sh
# Dashboard → http://localhost:9000
```

### Shutdown

```bash
./stop_xoyo.sh
```

---

## ▸ Service Catalog

<details>
<summary><strong>Lite Tier — 27 Services (8 GB RAM, No GPU)</strong></summary>
<br/>

All LLM inference is cloud-routed. No local GPU needed.

**Core Infrastructure**

| Service | Description |
|---|---|
| `orchestrator/main.py` | Central FastAPI hub — routes all requests, manages tools |
| `orchestrator/llm_router.py` | Zero-failure routing across 8 LLM providers |
| `services/mythos_os.py` | Unrestricted subsystem controller |
| `services/workers_massive.py` | Parallel task execution engine |

**Intelligence & Reasoning**

| Service | Description |
|---|---|
| `services/active_inference.py` | Free Energy Principle-based decision making |
| `services/debate_service.py` | Multi-agent adversarial reasoning |
| `services/hyperagents_dgm.py` | Deep Generative Model coordination |
| `services/math_services.py` | Symbolic + numerical computation |
| `services/nngpt_service.py` | Neural network GPT pipeline |
| `services/bmssp_solver.py` | Bounded-Memory Sequential Search |
| `services/diag2diag.py` | Diagnostic reasoning engine |

**Memory**

| Service | Description |
|---|---|
| `services/memory_manager.py` | Core memory CRUD operations |
| `services/memory_retrieval.py` | Semantic search over memories |
| `services/memory_personal.py` | User preference & context tracking |
| `services/memory_consolidator.py` | Sleep-cycle memory consolidation |
| `services/crystallization_daemon.py` | Converts experiences into reusable skills |

**Safety & Routing**

| Service | Description |
|---|---|
| `services/constitutional_ai.py` | Ethical guardrails and safety checks |
| `services/intent_bnn.py` | Bayesian Neural Network intent classifier |
| `services/flow_policy.py` | Conversation flow state machine |
| `services/priority_engine.py` | Task prioritization and scheduling |

**Tools & Agents**

| Service | Description |
|---|---|
| `services/desktop_control.py` | Mouse, keyboard, and window automation |
| `services/web_agent.py` | Autonomous web browsing and research |
| `services/google_agent.py` | Google Workspace integration |
| `services/office_agent.py` | Document editing and management |
| `services/ppt_generator.py` | PowerPoint presentation creation |
| `services/docx_generator.py` | Word document creation |
| `services/xoyo_agent_builder.py` | Create new specialized sub-agents |

**Watchdogs & Monitoring**

| Service | Description |
|---|---|
| `services/stuck_detector.py` | Detects and recovers hung tasks |
| `services/agent_trace.py` | Full execution tracing and logging |
| `services/task_doctor.py` | Diagnoses and heals failing tasks |
| `services/interrupt_fsm.py` | Finite State Machine for interrupts |
| `services/progress_vocalizer.py` | Announces task progress |
| `services/subagent_supervisor.py` | Manages child agent lifecycles |
| `services/system_monitor.py` | System resource monitoring |
| `services/ws_event_bridge.py` | WebSocket event bridge to frontend |
| `services/activity_stream.py` | Activity logging and streaming |
| `services/voice_pipeline.py` | Voice processing pipeline |

</details>

<details>
<summary><strong>Standard Tier — +8 Services (16 GB RAM, No GPU)</strong></summary>
<br/>

Deeper reasoning, scientific simulation, and autonomous exploration.

| Service | Description | RAM |
|---|---|---|
| `services/advanced_idle.py` | Autonomous learning during idle time | +200 MB |
| `services/bayesian_surprise.py` | Novelty detection for information gain | +150 MB |
| `services/dreamer_server.py` | World-model based planning | +250 MB |
| `services/physics_server.py` | Physics simulation engine | +150 MB |
| `services/materials_discovery.py` | Materials science computation | +200 MB |
| `services/era_engine.py` | Evolutionary Reasoning Architecture | +150 MB |
| `services/deep_research.py` | Multi-step autonomous research | +200 MB |
| `services/scene_generator.py` | 3D scene composition | +200 MB |

To enable: Uncomment these services in `start_xoyo.sh` or set `LITE_MODE = False`.

</details>

<details>
<summary><strong>Full Tier — +18 Services (32 GB+ RAM, CUDA GPU)</strong></summary>
<br/>

Real-time perception, speech, and local model inference. **Requires CUDA GPU with 6+ GB VRAM.**

**Perception & Voice**

| Service | Description | VRAM |
|---|---|---|
| `services/camera_server.py` | Live camera feed processing | GPU + Webcam |
| `services/yolo_server.py` | Real-time YOLOv8 object detection | 2 GB |
| `services/vision_server.py` | Multi-model vision routing | 2 GB |
| `services/screen_awareness.py` | Screen content understanding | 2 GB |
| `services/wakeword_server.py` | Voice activation ("Hey XOYO") | 1 GB |
| `services/whisper_server.py` | Whisper STT transcription | 2 GB |
| `services/neural_tts.py` | Text-to-speech synthesis | 1 GB |
| `services/prosody_server.py` | Emotional speech control | 1 GB |
| `services/affective_loop.py` | Emotion-aware response adaptation | 1 GB |
| `services/memory_advanced.py` | Long-term memory with local embeddings | 2 GB |

**Local LLM Inference**

| Service | Description | VRAM |
|---|---|---|
| `services/florence_server.py` | Florence-2 vision-language model | 4 GB |
| `services/mamba_server.py` | Mamba SSM inference | 4 GB |
| `services/rwkv_server.py` | RWKV linear attention model | 4 GB |
| `services/nitro_server.py` | Jan.ai Nitro local inference | 6 GB |
| `services/llm_server.py` | Generic local LLM endpoint | 6 GB |
| `services/smolvla_server.py` | SmolVLA vision-language-action | 4 GB |
| `services/dino_server.py` | DINOv2 visual features | 2 GB |
| `services/image_generator.py` | AI image generation | 6 GB |

To enable: Uncomment desired services in `start_xoyo.sh`. GPU services auto-detect CUDA and fail gracefully on CPU-only systems.

</details>

---

## ▸ Design Philosophy

<table>
  <tr>
    <td width="30%"><strong>Zero-Failure LLM Routing</strong></td>
    <td>Cascades through 8 providers with automatic retry, rate-limit awareness, and task-aware model selection. A single provider outage never kills the system.</td>
  </tr>
  <tr>
    <td><strong>Scale to Your Hardware</strong></td>
    <td>Runs on an 8 GB ultrabook. Uncomment services as your hardware grows. GPU perception and voice are fully optional.</td>
  </tr>
  <tr>
    <td><strong>Microservice Architecture</strong></td>
    <td>Each service is an independent process with its own port, communicating via Redis pub/sub and HTTP. Any service can crash without taking down the system.</td>
  </tr>
  <tr>
    <td><strong>Constitutional Safety</strong></td>
    <td>Every response passes through ethical guardrails. Destructive actions require explicit user permission.</td>
  </tr>
  <tr>
    <td><strong>Self-Healing</strong></td>
    <td>Crashed services are automatically restarted (3x retry). Stuck tasks are detected and recovered by the Task Doctor.</td>
  </tr>
</table>

---

## ▸ Project Structure

```
xoyo/
├── orchestrator/              Core brain — FastAPI hub + LLM Router
│   ├── main.py                2700+ line orchestrator
│   └── llm_router.py          Multi-provider routing engine
├── services/                  45+ independent microservices
│   ├── active_inference.py        Lite
│   ├── constitutional_ai.py       Lite
│   ├── dreamer_server.py          Standard
│   ├── yolo_server.py             Full (GPU)
│   └── ...
├── frontend/                  Web dashboard & landing page
├── xoyo_daemon.py             Service watchdog daemon
├── start_xoyo.sh              System launcher (tier-aware)
├── stop_xoyo.sh               Graceful shutdown
└── .env.example               API key template
```

---

## ▸ License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

<!-- Animated Footer -->
<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:161b22,50:1a1b27,100:0d1117&height=120&section=footer" />
