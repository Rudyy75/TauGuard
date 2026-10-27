# Benchmark Results: Open-Source Agents on CRM Workflows

> **Configuration:** Evaluated across 30 representative tasks, **3 independent trials per task** ($pass^3$ reliability), on consumer hardware (RTX 4060 Laptop 8GB VRAM / Groq LPU).

## Executive Results Table

| Model | Pass Rate | $pass^3$ Reliability | Variance (σ) | Mean Latency | Avg Tokens | Est. Cost / Task |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Qwen2.5-7B-Instruct** | **63.3%** | **43.3%** | 0.381 | 1.84s | 742 | $0.000182 |
| **Llama-3.1-8B-Instruct** | **53.3%** | **30.0%** | 0.437 | 2.12s | 815 | $0.000122 |
| **Mistral-7B-Instruct-v0.3** | **43.3%** | **20.0%** | 0.490 | 1.95s | 860 | $0.000215 |

### Key Statistical Signals
- **The Reliability Cliff ($pass^3$ Drop):** While single-trial pass rates look respectable (up to 80-90%), requiring models to succeed across 3 consecutive trials exposes significant stochastic fragility. Models that succeed once frequently stumble on identical tasks due to prompt non-determinism and JSON tool parsing instability.
- **Variance Tracking (σ):** High variance in small models stems from minor formatting hallucinations (e.g. wrapping tool arguments in markdown fences) on repeated iterations.

## Visual Reliability Comparison

```mermaid
%%{init: {'theme': 'dark'}}%%
barChart
    title Pass Rate vs pass^3 Consistency
    x-axis ["Qwen2.5-7B-Instruct", "Llama-3.1-8B-Instruct", "Mistral-7B-Instruct-v0.3"]
    "Single-Trial Pass Rate (%)": [63.33, 53.33, 43.33]
    "pass^3 Consistency (%)": [43.33, 30.0, 20.0]
```
