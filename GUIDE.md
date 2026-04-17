# 🚀 FRIDAY: Hardened Autonomous Agent Setup Guide

Welcome to the **FRIDAY v1.0** production-grade setup guide. FRIDAY is a local-first, memory-powered, and skill-dynamic terminal AI assistant designed for secure and deterministic operations.

---

## 📋 Prerequisites

- **Python**: 3.10+
- **Groq API Key**: Required for high-speed LLM inference. Get one at [console.groq.com](https://console.groq.com).
- **Linux Environment**: Optimized for Linux bash/zsh environments.

---

## 🛠️ Installation

1. **Clone the Workspace**:
   If you have downloaded the source, navigate to the project directory:
   ```bash
   cd friday
   ```

2. **Setup Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## ⚙️ Configuration

1. **Environment Variables**:
   Copy the example environment file and add your key:
   ```bash
   cp .env.example .env
   # Open .env and set GROQ_API_KEY=your_key_here
   ```

2. **Model Catalog**:
   FRIDAY uses `groq_api_complete.json` to route tasks between "fast" (Llama 8B) and "strong" (Llama 70B) models. This is pre-configured for optimal performance.

---

## 🚀 Starting FRIDAY

Launch the interactive CLI:
```bash
python main.py
```

### Basic Commands
- `help`: Show all available commands.
- `status`: Check agent health, mode, and token budget.
- `skills`: List all loaded high-performance shell skills.
- `mode [safe|auto|build]`: Switch operational safety levels.
- `exit`: Securely shutdown the agent.

---

## 🛡️ Operational Modes

| Mode | Autonomy | Safety Guarantee |
| :--- | :--- | :--- |
| **SAFE** | Lowest | Requires `(y/n)` for **every** command. Hard-blocks traversals. |
| **AUTO** | Medium | Auto-runs safe/medium commands. Prompts ONLY for `sudo/rm`. |
| **BUILD** | Highest | Permits traversal warnings. Aggressively learns new skills. |

---

## 🔍 Advanced Features

### 🧠 Persistent Memory
FRIDAY uses **MemPalace** for long-term memory. It remembers successful command outcomes and context across restarts.

### ⚡ Dynamic Skills
FRIDAY can generate new skills on the fly. Check the `skills/` directory to see `.md` and `.sh` bundles.
- Use `skills` in the CLI to see triggers.

### 📅 Background Scheduler
FRIDAY can handle long-running tasks in the background. If a task fails, it supports automated retries and crash recovery locks.

### 🕵️ Trace Inspection
Every single decision FRIDAY makes is recorded. Check for JSON logs in:
`logs/traces/run-<uuid>.json`

---

## 🧪 Testing & Evaluation

### Offline Replay
Run a deterministic test against saved fixtures:
```bash
python -m tests.harness
```

### Empirical Evaluation
Run the full scenario-based evaluation suite to score accuracy and safety:
```bash
python eval/run_eval.py
```

---

## 📜 Behavior Contract
For detailed architectural invariants and safety guarantees, please refer to:
[docs/behavior_contract.md](docs/behavior_contract.md)
