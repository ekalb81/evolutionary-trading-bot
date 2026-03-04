---
name: dspy-prompt-optimizer
description: Model-agnostic DSpy-based prompt optimization using token-tracking with Dash-Claw compatibility
---

## Overview
A model-agnostic prompt optimizer powered by DSpy. It compiles the raw prompt, generates an optimized version, and records metrics in a Dash-Claw friendly `.jsonl` log.

It defaults to pulling an evaluation dataset directly from LangFuse (generation traces) and routes optimization through OpenRouter (supporting the `openrouter/auto` Auto Router for intelligent model selection).

## Environment Variables
Ensure these are set before running the optimizer:
- `OPENROUTER_API_KEY`: Required for the OpenRouter / DSpy backend.
- `LANGFUSE_PUBLIC_KEY`: LangFuse public key
- `LANGFUSE_SECRET_KEY`: LangFuse secret key
- `LANGFUSE_API_BASE`: (Optional) Custom LangFuse base URL; defaults to `https://cloud.langfuse.com`
- `LANGFUSE_PROJECT_ID`: (Optional) Specific project to pull data from.

## Trigger
Use when you want to optimize prompts across models and inspect token savings and quality trade-offs. 

## When to Use This Skill
- You want to reduce total prompt tokens without sacrificing quality
- Dash-Claw compatibility is required (log format: `.jsonl`)
- You may swap LLM backends via OpenRouter (or test via `openrouter/auto`)

## What It Produces
- `scripts/optimize_prompt.py` CLI
- `assets/` references as needed
- `runs.jsonl` data logs (Dash-Claw ready)

## How It Works (high level)
1. Accept a raw prompt and model spec
2. Fetch Ground Truth examples from LangFuse (falls back to synthetic data)
3. Use DSpy's COPRO optimizer for instruction tuning against the LangFuse dataset
4. Count tokens up front for raw vs optimized execution
5. Save a JSONL record with metrics, token delta, the optimized prompt text, and 10% sampling of IOs
6. Provide a summary via CLI

## Usage Example
```bash
python3 scripts/optimize_prompt.py --task "Summarize this technical article concisely" --model "openrouter/auto" --log_path runs.jsonl
```
