# NemotronCoder: Vision-Augmented Autonomous Coding Agent

[![Nebius Token Factory](https://img.shields.io/badge/Infrastructure-Nebius%20Token%20Factory-00E599?style=for-the-badge)](https://nebius.com)
[![NVIDIA Nemotron](https://img.shields.io/badge/Model-NVIDIA%20Nemotron-76B900?style=for-the-badge&logo=nvidia)](https://developer.nvidia.com)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/Dashboard-FastAPI-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

> **Built for the Nebius x NVIDIA Global AI Hackathon** — *Coding and Agentic Engineering Track*

---

## 🌟 Overview

**NemotronCoder** is an autonomous, vision-augmented coding agent engineered to interact directly with live web coding environments and programming benchmarks. Powered by **NVIDIA Nemotron** models running on **Nebius Token Factory**, NemotronCoder navigates browser-based code sandboxes, interprets visual and textual problem constraints, writes algorithmic solutions, and continuously self-heals compiler diagnostics in a closed execution feedback loop.

```
       ┌────────────────────────────────────────────────────────┐
       │                 Autonomous Web Agent                   │
       │           (Playwright Stealth + Vision OCR)            │
       └───────────────────────────┬────────────────────────────┘
                                   │ (Problem Scrape & Visual Prompts)
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │                  Nebius Token Factory                  │
       │    NVIDIA Nemotron (nvidia/nemotron-3-super-120b-a12b) │
       └───────────────────────────┬────────────────────────────┘
                                   │ (Optimized Algorithmic Code)
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │                In-Browser Execution                    │
       │         (Ace Editor Injection + Compiler Run)          │
       └───────────────────────────┬────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
              [Pass Tests]               [Compiler Error]
                    │                             │
             Next Challenge           Self-Healing Feedback Loop
                    │                  (Escalate Temperature,
                    ▼                  Incorporate Traceback)
         SQLite Telemetry Log                     │
                    ▲                             │
                    └─────────────────────────────┘
```

---

## 🚀 Key Features

* **⚡ Accelerated via Nebius Token Factory:** Leverages Nebius's high-throughput serverless endpoints (`api.tokenfactory.nebius.com`) to deliver rapid inference and minimal latency during iterative code generation.
* **🧠 NVIDIA Nemotron Reasoning:** Uses `nvidia/nemotron-3-super-120b-a12b` and `nvidia/Nemotron-3_5-Lightning` for multi-step algorithmic reasoning, edge-case anticipation, and code generation across C, C++, Python, and Java.
* **👁️ Multimodal & Visual Understanding:** Automatically captures and analyzes visual challenge checkpoints and math verification prompts using multimodal vision models.
* **🔄 Closed-Loop Self-Healing:** When compiler or test failures occur, the agent scrapes the diagnostic traceback, updates its memory context, dynamically escalates temperature, and re-synthesizes bug fixes until test cases pass.
* **🕹️ Stealth Browser Orchestration:** Integrates Playwright with stealth patches and realistic Gaussian typing distributions, mouse jitter, and natural delays to interact authentically with complex web editors (Ace Editor).
* **📊 Observability Dashboard:** Built-in FastAPI + SQLite web dashboard providing live telemetry on solve rate, session logs, retry counts, and system metrics.

---

## 🛠️ Tech Stack

* **Inference Platform:** [Nebius Token Factory](https://nebius.com) (`https://api.tokenfactory.nebius.com/v1/`)
* **AI Models:** NVIDIA Nemotron Family (`nvidia/nemotron-3-super-120b-a12b`, `nvidia/Nemotron-3_5-Lightning`), NVIDIA Vision
* **Browser Automation:** Playwright, Playwright Stealth
* **Backend & API:** Python 3.10+, FastAPI, Uvicorn, Jinja2
* **Storage & Telemetry:** SQLite3

---

## 📦 Quick Start Guide

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/NemotronCoder.git
cd NemotronCoder
```

### 2. Set Up Virtual Environment & Dependencies
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and supply your credentials:
```bash
cp .env.example .env
```

Edit `.env`:
```env
# Nebius Token Factory Credentials (Mandatory for Hackathon)
USE_NEBIUS=true
NEBIUS_API_KEY=your_nebius_api_key_here
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/

# NVIDIA Open Models
FAST_MODEL=nvidia/nemotron-3-super-120b-a12b
THINKING_MODEL=nvidia/nemotron-3-super-120b-a12b
```

### 4. Run the Observability Dashboard
To view live metrics, sessions, and telemetry:
```bash
uvicorn dashboard.app:app --host 0.0.0.0 --port 8000 --reload
```
Open [http://localhost:8000](http://localhost:8000) in your browser.

### 5. Launch the Autonomous Agent
```bash
python run_automation.py --count 5
```

---

## 📊 Live Observability Dashboard

The dashboard provides real-time oversight over the agent's autonomous execution:
* Real-time problem completion progress & pass/fail counts
* Token latency and model temperature monitoring
* Detailed execution logs with compiler error analysis and prompt debugging

---

## 📜 License

This project is open-source under the [MIT License](LICENSE).
