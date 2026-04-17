# FRIDAY Behavior Contract (v1.0)

This document formalizes the exact guarantees and boundaries that FRIDAY adheres to. All execution logic, planning, and safety policies are bound by this contract.

## 1. Operational Modes

FRIDAY operates under three distinct modes of autonomy.

### 🛡️ SAFE Mode (Default)
- **Guarantees**: 
  - Will never execute a command without explicit user confirmation (`y/n`).
  - Will never modify files outside of the defined `PROJECT_ROOT`.
  - Path traversal attempts (`../`) are hard-blocked.
  - Automatically denies commands longer than 300 characters.

### ⚙️ AUTO Mode
- **Guarantees**: 
  - Suppresses interactive prompts for "Safe" and "Medium" risk commands.
  - Commands flagged as "Dangerous" (e.g. destructive actions like `sudo` or `rm -rf`) **always** trigger an explicit user prompt.
  - Still adheres to the strict `PROJECT_ROOT` workspace boundary and traversal blocks.

### 🏗️ BUILD Mode
- **Guarantees**:
  - The agent is permitted minimal path traversal outside the project root explicitly for scaffolding infrastructure.
  - Treats workspace restriction violations as "Warning/Medium Risk" rather than "Dangerous/Blocked".
  - Aggressively mints and saves new skills based on observed behavior without rigid scope validation.
  - "Dangerous" regex matches (e.g. `sudo`, deletions) still require explicit user confirmation.

---

## 2. Invariants

FRIDAY guarantees the following invariants, meaning they cannot be bypassed by any LLM hallucination:

### Safety Invariants
- **No Direct Execution**: The LLM output is purely structural JSON parameters (`{"type": "filesystem", "action": "create_directory"}`). The LLM *cannot* directly pipeline strings into a live shell.
- **Environment Sanitation**: Native shell processes are launched with sanitized environments, effectively neutralizing `LD_PRELOAD`, `BASH_ENV`, and `PROMPT_COMMAND` injection payloads.

### Scheduler Invariants
- **Silent Background Execution**: Tasks processed automatically by the `TaskScheduler` will never interrupt the foreground CLI by streaming to `sys.stdout`. Events are cleanly rendered when the `friday >` prompt is redrawn.
- **Idempotency Leases**: Every task run in the background is "locked" upon start. If the application crashes, a stale lock releases after 5 minutes (300 seconds), preventing the agent from concurrently repeating jobs.

### Memory & State Invariants
- **Zero-knowledge Network Execution**: Aside from the explicitly declared API paths (Groq/OpenAI completions), FRIDAY does not initiate outbound telemetry or logging to the cloud. All persistent state (`state.json`, `budget.json`, `tasks.json`) and vector knowledge (`logs/traces/`, `memory/`) exist purely on the local disk.
