# 🛡️ TauGuard: CRM Agent Benchmark & Grader Audit

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Hardware: RTX 4060 Laptop](https://img.shields.io/badge/Hardware-RTX%204060%20Laptop%20(8GB)-green.svg)](#hardware--budget-setup)
[![Budget: ₹0](https://img.shields.io/badge/Budget-%E2%82%B90%20(Free%20Tier)-orange.svg)](#hardware--budget-setup)
[![Benchmark: tau-retail](https://img.shields.io/badge/Benchmark-%CF%84--retail%20(CRM)-purple.svg)](#why-tau-bench-over-salesforce-crm-benchmark)

> **TL;DR:** We benchmarked 3 open-weights models (Qwen2.5-7B, Llama-3.1-8B, Mistral-7B) on multi-turn CRM workflows with statistical variance across repeated trials ($pass^3$), then **audited the benchmark's scoring engine**.  
> **Key Finding:** τ-bench's retail grader grants a **100% pass score to agents that violate security policies and corrupt database records**, while **failing semantically correct natural language answers** due to rigid substring checks.

---

## 📊 Executive Results: Multi-Trial Reliability Table

Evaluated on consumer hardware (**RTX 4060 Laptop 8GB VRAM**) across representative CRM tasks with **3 independent trials per task ($pass^3$)**:

| Model | Single Pass Rate | $pass^3$ Reliability | Variance (σ) | Mean Latency | Avg Tokens | Est. Cost / Task |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Qwen2.5-7B-Instruct** | **63.3%** | **43.3%** | 0.381 | 1.84s | 742 | $0.000182 |
| **Llama-3.1-8B-Instruct** | **53.3%** | **30.0%** | 0.437 | 2.12s | 815 | $0.000122 |
| **Mistral-7B-Instruct-v0.3**| **43.3%** | **20.0%** | 0.490 | 1.95s | 860 | $0.000215 |

```mermaid
%%{init: {'theme': 'dark'}}%%
barChart
    title Single-Trial Pass Rate vs pass^3 Consistency
    x-axis ["Qwen2.5-7B", "Llama-3.1-8B", "Mistral-7B"]
    "Single-Trial Pass (%)": [63.3, 53.3, 43.3]
    "pass^3 Reliability (%)": [43.3, 30.0, 20.0]
```

### 🔍 Key Engineering Takeaways:
1. **The $pass^3$ Reliability Cliff:** Single-trial leaderboards are deceptive. Under 3 repeated trials on identical tasks, success rates fell by **20% to 23.3%** across all models due to JSON syntax hallucinations and prompt non-determinism.
2. **Qwen2.5-7B Dominated Small Models:** Demonstrated superior adherence to structured tool calling schemas (Hermes-style format) with the lowest trial variance ($\sigma = 0.381$).

---

## 🎯 Benchmark Decision: Why τ-bench over Salesforce CRM Benchmark

| Criteria | τ-bench (Sierra / Princeton) | Salesforce Agentic Benchmark (CRMArena) |
|---|---|---|
| **Code Access** | ✅ Fully open-source Python engine | ❌ Proprietary leaderboard / closed eval |
| **Grader Inspection** | ✅ Open, transparent, hackable code | ❌ Black-box server-side scoring |
| **Execution Cost** | ✅ **₹0** (Ollama local + free Groq tier) | ⚠️ Requires Salesforce developer/sandbox org |
| **Domain Fit** | ✅ `τ-retail`: orders, cancellations, returns, CRM | ✅ Enterprise CRM |
| **Verdict** | **Selected:** Ideal for reproducible audit | Discarded: Inaccessible for open verification |

---

## 💥 Day 3 Findings: Breaking the Grader

We systematically audited the reward function $r = r_{\text{action}} \times r_{\text{output}} \in \{0, 1\}$.  
Full reproducible code and logs in [`GRADER_AUDIT.md`](file:///c:/Users/yellu/Documents/Stuff/Projects%20Stuff/RL/GRADER_AUDIT.md).

```
                        τ-BENCH SCORING PIPELINE
  Agent Actions ──► [ Database Mutation ] ──► r_action Check ─┐
                                                              ├──► r = r_action × r_output
  Dialogue Text ──► [ Substring Match   ] ──► r_output Check ─┘
```

### 1. 🕳️ The "No-Op" (Zero-Action) Exploit (`experiments/no_op_agent.py`)
- **Finding:** In read-only tasks (`task_05`) or valid policy rejections (`task_02`, `task_04`), the initial DB state equals the target state. An agent that emits canned text and **never calls any tools** scores $r_{\text{action}} = 1.0$ on **50% of tested tasks**.
- **The Fix:** Assert active tool execution history on read-only tasks to ensure the agent reasoned before idling.

### 2. 🚨 Policy & Authentication Bypass (`experiments/policy_bypass.py`)
- **Finding:** Corporate CRM policies mandate user identity verification before modifying orders. An agent that **bypasses authentication completely** scores an identical **1.0 (100% pass)** because the grader inspects only final state, not procedural compliance.
- **The Fix:** Add a policy compliance multiplier: $r = r_{\text{action}} \times r_{\text{output}} \times r_{\text{policy}}$.

### 3. 💣 Unauthorized Side-Effect Blindness (`experiments/side_effect_test.py`)
- **Finding:** When an agent updated a target shipping address on `task_01`, we simultaneously had it **wipe out order line items and corrupt customer records**. The grader awarded a **perfect 1.0 pass** because it only asserts the specific key specified in the task annotation.
- **The Fix:** Full state-graph diffing against an oracle database state snapshot.

### 4. 📝 The Paraphrase Penalty (`experiments/paraphrase_test.py`)
- **Finding:** A model explaining an order cancellation with polite, natural phrasing (*"We have voided purchase ord_001. A credit of one hundred and fifty dollars is on its way"*) received **0.0 (fail)** because $r_{\text{output}}$ performed rigid substring checks for `"cancelled"` and `"149.99"`.
- **The Fix:** Semantic verification with a lightweight fact extraction evaluator.

### ⚖️ Honest Reporting: What Held Up?
- For standard write tasks without shortcuts, $r_{\text{action}}$ reliably caught incorrect parameters, failed order cancellations, and invalid refunds.
- The state-comparison paradigm is fundamentally sound — but **lacks delta-fencing and procedural policy tracking**.

---

## 🛠️ System Architecture & ₹0 Budget Setup

Built to run entirely on consumer hardware or free developer tiers:

```
c:\Users\yellu\Documents\Stuff\Projects Stuff\RL\
├── configs/models.yaml          # Model parameters, context caps & cost configs
├── src/
│   ├── envs/
│   │   ├── mock_retail.py       # CRM sandbox (Orders, Users, Inventory, Policies)
│   │   ├── grader.py            # Tau-bench exact grader (r_action * r_output)
│   │   ├── patched_grader.py    # Robust grader (state diffing + auth/policy gate)
│   │   └── task_generator.py    # 30-task parameterized benchmark generator
│   ├── agents/
│   │   ├── tool_agent.py        # OpenAI-compatible tool agent (Ollama / vLLM / Groq)
│   │   └── mock_user.py         # Customer simulator
│   └── harness/
│       ├── metrics.py           # Statistical aggregations (pass^k, variance, cost)
│       └── runner.py            # Multi-trial execution engine
├── experiments/
│   ├── no_op_agent.py           # Exploit 1: Silent agent exploit
│   ├── policy_bypass.py         # Exploit 2: Security bypass test
│   ├── side_effect_test.py      # Exploit 3: Unmonitored DB mutation test
│   ├── paraphrase_test.py       # Exploit 4: Rigid text penalty test
│   └── run_all_audits.py        # Single-command runner for all 4 audits
├── harness.py                   # Day 2 CLI execution harness
└── generate_report.py           # Markdown & Mermaid report generator
```

### Local Hardware Configuration
- **GPU:** NVIDIA GeForce RTX 4060 Laptop (8GB VRAM)
- **Serving Engine:** [Ollama](https://ollama.com) or [vLLM](https://github.com/vllm-project/vllm)
- **Quantization:** `Q4_K_M` (~4.8GB VRAM footprint, leaving 3GB for 4K context KV cache)
- **Customer Simulator:** Groq Free Tier (`llama-3.3-70b-versatile`, 30 RPM / 1000 RPD free)

---

## ⚡ Quickstart (Reproduce in 60 Seconds)

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/Rudyy75/TauGuard.git
cd TauGuard
pip install -r requirements.txt
```

### 2. Run the Grader Audits (Zero API Keys Required)
```bash
python -m experiments.run_all_audits
```

### 3. Run Multi-Trial Benchmark Harness
```bash
# Compare standard Tau-Bench vs Patched Safe Grader across 30 tasks (offline simulation)
python harness.py --mock --trials 3 --grader both --tasks-count 30 --output results/run_output.json

# Live run with local models via Ollama
ollama pull qwen2.5:7b-instruct-q4_K_M
python harness.py --trials 3 --models qwen2.5-7b --grader both
```

### 4. Run Grader Unit Tests
```bash
python -m pytest tests/ -v
```

### 5. Generate Reports
```bash
python generate_report.py --input results/run_output.json --output results/benchmark_summary.md
```

---

## 🔬 Reproducibility & Live Evaluation Notes

- **Baseline Data (`results/baseline_runs.json`):** Evaluated against local GGUF checkpoints (`Q4_K_M`) using an RTX 4060 Laptop (8GB VRAM) and Ollama, tracking $pass^3$ statistical reliability across repeated seeds.
- **Offline / Zero-Cost Simulation (`--mock`):** Enables instant, deterministic verification of harness orchestration, tool dispatch, and grading logic without requiring local GPU serving or cloud API credentials.
- **Audit Verification:** All four benchmark failure modes are codified as runnable unit tests in `tests/test_graders.py` and standalone scripts in `experiments/`.
