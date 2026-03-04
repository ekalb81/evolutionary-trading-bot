#!/usr/bin/env python3
import json
import random
import os
import sys
import argparse
import time
from pathlib import Path
import urllib.request
import urllib.error
import urllib.parse
import base64

# Set up OpenRouter key before importing dspy/litellm to avoid auth errors
or_key = os.environ.get("OPENROUTER_API_KEY")
if or_key:
    os.environ["OPENAI_API_KEY"] = or_key

try:
    import tiktoken
except ImportError:
    tiktoken = None

def count_tokens(text: str) -> int:
    if not text: return 0
    if tiktoken is not None:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            pass
    return max(1, len(text) // 4)

def basic_auth_header(public_key: str, secret_key: str) -> str:
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode('ascii')
    return f"Basic {token}"

def extract_text_from_node(node):
    """Safely extracts a flat string from deeply nested LangFuse i/o structures like [{'role': 'user', 'content': '...'}]"""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    elif isinstance(node, list):
        items = [extract_text_from_node(item) for item in node]
        return "\n".join([i for i in items if i])
    elif isinstance(node, dict):
        if "content" in node:
            return extract_text_from_node(node["content"])
        if "messages" in node:
            return extract_text_from_node(node["messages"])
        if "text" in node:
            return extract_text_from_node(node["text"])
        # Fallback to json dump for unknown object shapes
        return json.dumps(node, ensure_ascii=False)
    return str(node)

def fetch_langfuse_dataset(limit=20, page_size=20, max_pages=5, retry_limit=3):
    lang_id = os.environ.get("LANGFUSE_PROJECT_ID", None)
    lang_public = os.environ.get("LANGFUSE_PUBLIC_KEY", None)
    lang_secret = os.environ.get("LANGFUSE_SECRET_KEY", None)
    lang_base = os.environ.get("LANGFUSE_API_BASE") or os.environ.get("LANGFUSE_HOST") or "https://us.cloud.langfuse.com"
    
    dataset = []
    
    if not (lang_public and lang_secret):
        print("[Warn] LangFuse credentials not found in env.", file=sys.stderr)
        return dataset

    auth_header = basic_auth_header(lang_public, lang_secret)
    headers = {"Authorization": auth_header}

    # Using v1 observations endpoint (has full input/output payloads)
    base_url = f"{lang_base}/api/public/observations"
    
    for page in range(1, max_pages + 1):
        attempts = 0
        success = False
        url = f"{base_url}?type=GENERATION&limit={page_size}&page={page}"
        print(f"[Debug] Querying LangFuse: {url}", file=sys.stderr)
        
        while attempts < retry_limit and not success:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp_data = json.loads(resp.read().decode('utf-8'))
                    data = resp_data.get("data", [])
                    print(f"[Debug] Received {len(data)} items on page {page}", file=sys.stderr)
                    
                    for obs in data:
                        input_raw = obs.get("input")
                        output_raw = obs.get("output")
                        
                        prompt_text = extract_text_from_node(input_raw)
                        response_text = extract_text_from_node(output_raw)
                        
                        if prompt_text.strip() and response_text.strip():
                            dataset.append({"input": prompt_text, "output": response_text})
                            
                    success = True
            except urllib.error.HTTPError as e:
                print(f"[Warn] Fetch page {page} failed: {e.code}", file=sys.stderr)
                time.sleep(1)
            except Exception as e:
                print(f"[Warn] Fetch exception: {e}", file=sys.stderr)
                time.sleep(1)
            attempts += 1
            
        if not success or len(dataset) >= limit:
            break

    return dataset[:limit]


def load_or_generate_data(dataset_path, task):
    data = fetch_langfuse_dataset(limit=20)
    if data:
        print(f"\n[Info] Successfully loaded {len(data)} valid ground-truth examples from LangFuse.", file=sys.stderr)
        return data

    if dataset_path and Path(dataset_path).exists():
        data = []
        with open(dataset_path, "r") as f:
            for line in f:
                if line.strip(): data.append(json.loads(line))
        return data
    
    print(f"[Info] Generating synthetic examples for testing the optimizer...", file=sys.stderr)
    return [
        {"input": f"{task} - example 1", "output": "Expected output 1"},
        {"input": f"{task} - example 2", "output": "Expected output 2"},
        {"input": f"{task} - example 3", "output": "Expected output 3"},
        {"input": f"{task} - example 4", "output": "Expected output 4"},
        {"input": f"{task} - example 5", "output": "Expected output 5"},
    ]

def evaluate_exact_match(example, pred, trace=None):
    # Lenient evaluate for messy text dumps
    return example.output.strip()[:20].lower() in pred.output.strip().lower()

def run_dspy_optimization(task, model_name, dataset, sampling_ratio):
    try:
        import dspy
        from dspy.teleprompt import COPRO
    except ImportError:
        print("[Error] DSpy is not installed. Please run: pip install dspy-ai", file=sys.stderr)
        sys.exit(1)

    # Get API key - must be set in environment for LiteLLM to work
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("[Warn] OPENROUTER_API_KEY not found in environment. DSpy optimization will fail.", file=sys.stderr)
        raise RuntimeError("Missing OPENROUTER_API_KEY - required for DSpy to call LLM")
    
    # Configure LiteLLM for OpenRouter
    # When model is "openrouter/xxx", litellm will use its OpenRouter integration
    lm = dspy.LM(
        model_name,  # e.g., "openrouter/auto" or "openrouter/anthropic/claude-3-haiku"
        api_key=api_key
    )
    dspy.settings.configure(lm=lm)

    examples = [dspy.Example(input=d["input"], output=d["output"]).with_inputs("input") for d in dataset]
    
    split_idx = int(len(examples) * 0.8)
    trainset = examples[:split_idx]
    if not trainset: trainset = examples 

    class BasicTask(dspy.Signature):
        """Perform the task optimally based on the input."""
        input = dspy.InputField(desc=task)
        output = dspy.OutputField()

    class TaskModule(dspy.Module):
        def __init__(self):
            super().__init__()
            self.prog = dspy.ChainOfThought(BasicTask)
            
        def forward(self, input):
            return self.prog(input=input)

    optimizer = COPRO(
        metric=evaluate_exact_match,
        breadth=2,
        depth=1,
        init_prompts=[task]
    )
    
    print(f"[Info] Starting DSpy COPRO compilation on {len(trainset)} LangFuse examples...", file=sys.stderr)
    compiled_module = optimizer.compile(
        student=TaskModule(),
        trainset=trainset,
        eval_kwargs={"num_threads": 1, "display_progress": False}
    )

    try:
        optimized_instruction = compiled_module.prog.signature.instructions
    except Exception:
        optimized_instruction = task + " (Optimized by DSpy)"

    sample_size = max(1, int(len(trainset) * sampling_ratio))
    sample_dev = random.sample(trainset, min(sample_size, len(trainset)))
    
    samples_out = []
    correct_count = 0
    for ex in sample_dev:
        try:
            pred = compiled_module(input=ex.input)
            is_correct = evaluate_exact_match(ex, pred)
            if is_correct: correct_count += 1
            samples_out.append({
                "input": ex.input[:200] + "..." if len(ex.input) > 200 else ex.input,
                "output": getattr(pred, "output", str(pred))[:200] + "...",
                "expected": ex.output[:100] + "...",
                "correct": is_correct
            })
        except Exception as e:
            samples_out.append({"input": ex.input[:100], "error": str(e)})

    eval_score = correct_count / max(1, len(sample_dev))

    return optimized_instruction, samples_out, eval_score

def main():
    parser = argparse.ArgumentParser(description="DSpy Prompt Optimizer")
    parser.add_argument("--task", required=True, help="Raw prompt or base task description")
    parser.add_argument("--model", required=True, help="Model name (e.g. openrouter/auto)")
    parser.add_argument("--log_path", required=True, help="Path to runs.jsonl")
    parser.add_argument("--dataset", default="", help="Path to JSONL dataset for training/eval")
    parser.add_argument("--ratio", type=float, default=0.2, help="Sampling ratio for Dash-Claw JSON logging (default 0.2)")
    args = parser.parse_args()

    dataset = load_or_generate_data(args.dataset, args.task)
    raw_tokens = count_tokens(args.task)

    try:
        optimized_prompt, samples, score = run_dspy_optimization(
            args.task, args.model, dataset, args.ratio
        )
    except Exception as e:
        import traceback
        print(f"[Warning] DSpy optimization failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        optimized_prompt = args.task + "\n\n(Note: DSpy run failed - check API key)"
        samples = [{"input": d["input"][:100], "output": "Fallback"} for d in dataset[:1]]
        score = 0.0

    opt_tokens = count_tokens(optimized_prompt)
    delta = raw_tokens - opt_tokens

    record = {
        "raw_prompt_tokens": raw_tokens,
        "optimized_prompt_tokens": opt_tokens,
        "token_delta": {
            "absolute": delta, 
            "percent": (delta / raw_tokens * 100) if raw_tokens else 0
        },
        "samples": samples,
        "evaluation_score": score,
        "optimized_prompt": optimized_prompt
    }

    log_file = Path(args.log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    
    print(json.dumps(record, indent=2))

if __name__ == "__main__":
    main()