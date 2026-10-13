#!/usr/bin/env python3
"""Sequential real-Maya benchmarks; JSON evidence must live outside the checkout.

Examples:
  python3 scripts/bench-maya.py --label mtp --output /tmp/maya-mtp.json
  python3 scripts/bench-maya.py --scenarios retrieval --retrieval-sizes 64k,128k \
      --context-size 131072 --output /tmp/maya-retrieval.json

Sizes are total token budgets (K = 1024), including --max-tokens and eight
engine slack tokens. /api/tokens counts the complete rendered chat exactly.
Optionally use the trusted pinned Maya checkout and its tokenizer with
--maya-root /opt/maya --tokenizer-dir /data/path/tokenizer, running this helper
under /opt/maya/.venv/bin/python. HTTP itself requires only Python's stdlib.
No generated code is exec/eval'ed: a bounded AST interpreter in a timeout-limited
subprocess accepts only the small expression language requested by the tasks.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


class BenchError(Exception):
    pass


def token_size(text):
    text = text.strip().lower()
    match = re.fullmatch(r"([0-9]+)(k)?", text)
    if not match:
        raise argparse.ArgumentTypeError("expected an integer or size such as 8k")
    value = int(match[1]) * (1024 if match[2] else 1)
    if value < 1:
        raise argparse.ArgumentTypeError("size must be positive")
    return value


def size_list(text):
    return [token_size(part) for part in text.split(",")]


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_report(path, report):
    # Atomic and private, including when overwriting an older permissive file.
    fd, name = tempfile.mkstemp(prefix=".maya-bench-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            os.fchmod(file.fileno(), 0o600)
            json.dump(report, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Client:
    def __init__(self, base_url, key, timeout):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise BenchError("base URL must be an http(s) service URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise BenchError("base URL must not contain credentials, query, or fragment")
        self.base = base_url.rstrip("/")
        if self.base.endswith("/v1"):
            self.base = self.base[:-3]
        self.key, self.timeout = key, timeout
        self.opener = urllib.request.build_opener()

    def open(self, route, body=None):
        headers = {"Accept": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + route, data=data, headers=headers)
        try:
            return self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            evidence = error.read(1024 * 1024).decode("utf-8", "replace")
            if self.key:
                evidence = evidence.replace(self.key, "[REDACTED]")
            raise BenchError(f"{route}: HTTP {error.code}: {evidence}") from error

    def json(self, route, body=None):
        with self.open(route, body) as response:
            value = json.loads(response.read())
        if not isinstance(value, dict):
            raise BenchError(f"{route}: expected a JSON object")
        return value

    def stream(self, body, result):
        started = time.perf_counter()
        result.update(ttft_seconds=None, first_generated_field=None, total_seconds=None,
                      content="", reasoning_content="", usage={}, timings={},
                      finish_reason=None, stream_done=False, events=[])
        content, reasoning = [], []

        def consume(lines):
            if not lines:
                return False
            data = "\n".join(lines)
            elapsed = time.perf_counter() - started
            if data.strip() == "[DONE]":
                result["stream_done"] = True
                return True
            chunk = json.loads(data)
            if not isinstance(chunk, dict):
                raise BenchError("stream event is not an object")
            result["events"].append({"elapsed_seconds": elapsed, "chunk": chunk})
            if chunk.get("error"):
                raise BenchError("stream error: " + json.dumps(chunk["error"], ensure_ascii=False))
            if isinstance(chunk.get("usage"), dict):
                result["usage"].update(chunk["usage"])
            if isinstance(chunk.get("timings"), dict):
                result["timings"].update(chunk["timings"])
            for choice in chunk.get("choices") or []:
                if choice.get("index", 0) != 0:
                    continue
                if choice.get("finish_reason") is not None:
                    result["finish_reason"] = choice["finish_reason"]
                delta = choice.get("delta") or {}
                for field, parts in (("reasoning_content", reasoning), ("content", content)):
                    text = delta.get(field)
                    if isinstance(text, str) and text:
                        if result["ttft_seconds"] is None:
                            result["ttft_seconds"] = elapsed
                            result["first_generated_field"] = field
                        parts.append(text)
            return False

        try:
            with self.open("/v1/chat/completions", body) as response:
                if "text/event-stream" not in response.headers.get("Content-Type", ""):
                    raise BenchError("stream request did not return text/event-stream: " +
                                     response.read(1024 * 1024).decode("utf-8", "replace"))
                result["http_status"] = response.status
                lines = []
                while True:
                    if time.perf_counter() - started > self.timeout:
                        raise BenchError("stream exceeded request deadline")
                    raw = response.readline(2 * 1024 * 1024 + 1)
                    if len(raw) > 2 * 1024 * 1024:
                        raise BenchError("stream line exceeds 2 MiB")
                    if not raw:
                        consume(lines)
                        break
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if not line:
                        if consume(lines):
                            break
                        lines = []
                    elif line.startswith("data:"):
                        lines.append(line[5:].lstrip(" "))
                    # Ignore SSE comments/heartbeats, event names and empty role deltas.
        finally:
            result["total_seconds"] = time.perf_counter() - started
            result["content"] = "".join(content)
            result["reasoning_content"] = "".join(reasoning)


class Counter:
    def __init__(self, client, args, probe):
        self.client = client
        self.local = None
        self.warning = None
        if args.maya_root or args.tokenizer_dir:
            if not (args.maya_root and args.tokenizer_dir):
                raise BenchError("--maya-root and --tokenizer-dir must be supplied together")
            root = Path(args.maya_root).resolve()
            sys.path.insert(0, str(root / "tools"))
            sys.path.insert(0, str(root))
            from strata_tokenizer import Tokenizer
            from serve.frontend import ChatTemplate, openai_to_messages
            tok = Tokenizer.from_dir(args.tokenizer_dir)
            template = ChatTemplate(Path(args.tokenizer_dir) / "chat_template.jinja")

            def local(body):
                messages, tools, kwargs = openai_to_messages(body)
                rendered = template.render(messages, tools=tools, **kwargs)
                return len(tok.encode(rendered, parse_special=True))

            self.local = local
            self.source = "upstream_local_rendered_chat"
        else:
            try:
                info = client.json("/api/tokens", probe)
            except BenchError as error:
                # Only a missing endpoint permits approximation. Auth/server failures are real failures.
                if "HTTP 404:" not in str(error) and "HTTP 405:" not in str(error):
                    raise
                self.warning = str(error)
                self.source = "approximate_utf8_bytes_div_4"
            else:
                if info.get("approximate") or not isinstance(info.get("tokens"), int):
                    raise BenchError("/api/tokens did not supply an exact text token count")
                self.source = "maya_api_tokens_rendered_chat"
                self.server_context = int(info.get("max_context") or 0)
        self.context = args.context_size or 0
        if self.source == "maya_api_tokens_rendered_chat":
            self.context = min(self.context, self.server_context) if self.context and self.server_context else (
                self.context or self.server_context)
        else:
            try:
                props = client.json("/props")
            except BenchError as error:
                if not self.context or ("HTTP 404:" not in str(error) and "HTTP 405:" not in str(error)):
                    raise
                discovered = 0
            else:
                discovered = int((props.get("default_generation_settings") or {}).get("n_ctx") or 0)
            self.context = min(self.context, discovered) if self.context and discovered else self.context or discovered
        if not self.context:
            raise BenchError("could not discover context capacity; supply --context-size")

    def count(self, body):
        if self.local:
            return {"tokens": self.local(body), "exact": True, "source": self.source}
        if self.source == "maya_api_tokens_rendered_chat":
            info = self.client.json("/api/tokens", body)
            if info.get("approximate") or not isinstance(info.get("tokens"), int):
                raise BenchError("exact text counting became unavailable")
            if info.get("max_context") and int(info["max_context"]) != self.server_context:
                raise BenchError("service context changed during benchmark")
            return {"tokens": info["tokens"], "exact": True, "source": self.source}
        byte_count = sum(len(message["content"].encode("utf-8")) for message in body["messages"])
        # Byte-BPE cannot require more than one token per input byte. Generous reserve
        # for the unmeasured chat template; not an exact near-capacity measurement.
        return {"tokens": math.ceil(byte_count / 4) + 64, "exact": False,
                "source": self.source, "conservative_budget_tokens": byte_count + 4096}


def request_body(model, prompt, args):
    return {"model": model, "messages": [{"role": "user", "content": prompt}],
            "stream": True, "stream_options": {"include_usage": True},
            "temperature": 0, "seed": args.seed, "reasoning_effort": args.reasoning_effort,
            "max_tokens": args.max_tokens}


def fixed_tasks():
    return [
        {"id": "japanese-math", "scenario": "japanese", "kind": "json",
         "prompt": "次の問題を解き、説明なしでJSONだけを返してください。税込価格は税抜1200円の10%増しです。そこから税込価格の25%を値引きしました。最終価格（円）を整数のpriceに入れてください。",
         "expected": {"price": 990}},
        {"id": "japanese-instructions", "scenario": "japanese", "kind": "json",
         "prompt": "説明なしでJSONだけを返してください。数列 [17, 4, 9, 12, 3, 8] から偶数だけを取り出して昇順に並べた配列をevenに入れてください。",
         "expected": {"even": [4, 8, 12]}},
        {"id": "code-filter-squares", "scenario": "code", "kind": "code",
         "prompt": "Write Python function nonnegative_squares(values): given a list of integers, return squares of nonnegative elements in original order, keeping duplicates. Return only the function, optionally a python fence. Its body MUST be a single return expression, using an ordinary list comprehension, arithmetic and comparisons; no imports, attributes, other functions, or statements.",
         "function": "nonnegative_squares", "parameters": ["values"],
         "cases": [{"args": [[]], "expected": []}, {"args": [[-3, 0, 2, -1, 2, 5]], "expected": [0, 4, 4, 25]},
                   {"args": [[-10, -2]], "expected": []}, {"args": [[7, 1, 0]], "expected": [49, 1, 0]}]},
        {"id": "code-clamp", "scenario": "code", "kind": "code",
         "prompt": "Write Python function clamp(value, lower, upper): return value limited to the inclusive interval [lower, upper], where lower <= upper. Return only the function, optionally a python fence. Its body MUST be one return expression. Only integer arithmetic, comparisons, conditional expressions and calls to min/max/abs are allowed; no imports, attributes, or other statements.",
         "function": "clamp", "parameters": ["value", "lower", "upper"],
         "cases": [{"args": [-9, -3, 4], "expected": -3}, {"args": [8, -3, 4], "expected": 4},
                   {"args": [2, -3, 4], "expected": 2}, {"args": [0, 0, 0], "expected": 0},
                   {"args": [-5, -7, -2], "expected": -5}]},
    ]


def unfence(text):
    text = text.strip()
    match = re.fullmatch(r"```(?:python|json)?\s*\n(.*?)\n```", text, re.DOTALL)
    return match[1].strip() if match else text


def exact_equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(exact_equal(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(exact_equal(left, right) for left, right in zip(actual, expected))
    return actual == expected


def expression(node, scope, fuel):
    # Never compile, eval, exec, resolve attributes, or invoke generated functions.
    fuel[0] -= 1
    if fuel[0] < 0:
        raise ValueError("AST evaluation operation limit reached")
    if isinstance(node, ast.Constant) and type(node.value) in (int, bool):
        if isinstance(node.value, int) and abs(node.value) > 10**12:
            raise ValueError("integer too large")
        return node.value
    if isinstance(node, ast.Name) and node.id in scope:
        return scope[node.id]
    if isinstance(node, ast.List):
        return [expression(item, scope, fuel) for item in node.elts]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
        value = expression(node.operand, scope, fuel)
        return -value if isinstance(node.op, ast.USub) else +value if isinstance(node.op, ast.UAdd) else not value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Pow)):
        left, right = expression(node.left, scope, fuel), expression(node.right, scope, fuel)
        if type(left) is not int or type(right) is not int:
            raise ValueError("arithmetic requires integers")
        if abs(left) > 10**12 or abs(right) > 10**12 or isinstance(node.op, ast.Pow) and not 0 <= right <= 8:
            raise ValueError("arithmetic bounds exceeded")
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        return left**right
    if isinstance(node, ast.Compare):
        left = expression(node.left, scope, fuel)
        for op, rhs in zip(node.ops, node.comparators):
            right = expression(rhs, scope, fuel)
            if isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            elif isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            else:
                raise ValueError("unsupported comparison")
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        branch = node.body if expression(node.test, scope, fuel) else node.orelse
        return expression(branch, scope, fuel)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        allowed = {"min": min, "max": max, "abs": abs}
        if node.func.id in allowed and 1 <= len(node.args) <= 3:
            return allowed[node.func.id](*(expression(arg, scope, fuel) for arg in node.args))
    if isinstance(node, ast.ListComp) and len(node.generators) == 1:
        generator = node.generators[0]
        if not isinstance(generator.target, ast.Name) or generator.is_async:
            raise ValueError("only a simple synchronous comprehension is supported")
        values = expression(generator.iter, scope, fuel)
        if not isinstance(values, list) or len(values) > 100:
            raise ValueError("comprehension requires a bounded list")
        out = []
        for value in values:
            nested = dict(scope, **{generator.target.id: value})
            if all(expression(condition, nested, fuel) for condition in generator.ifs):
                out.append(expression(node.elt, nested, fuel))
        return out
    raise ValueError("unsupported AST node: " + type(node).__name__)


def code_worker():
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
            resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
            if sys.platform.startswith("linux"):
                resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        except ImportError:
            pass
        payload = json.loads(sys.stdin.read(131073))
        tree = ast.parse(unfence(payload["code"]))
        if len(list(ast.walk(tree))) > 500 or len(tree.body) != 1:
            raise ValueError("expected one bounded function")
        func = tree.body[0]
        if not isinstance(func, ast.FunctionDef) or func.name != payload["function"]:
            raise ValueError("wrong function name or missing function")
        args = func.args
        if ([arg.arg for arg in args.args] != payload["parameters"] or args.posonlyargs or
                args.kwonlyargs or args.vararg or args.kwarg or args.defaults or args.kw_defaults or
                func.decorator_list or len(func.body) != 1 or not isinstance(func.body[0], ast.Return)):
            raise ValueError("expected the specified parameters and one return statement")
        # Annotations and any unsupported dead branch are also refused; nothing is executed.
        allowed_nodes = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return,
                         ast.Constant, ast.Name, ast.Load, ast.Store, ast.List, ast.ListComp,
                         ast.comprehension, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.Call,
                         ast.Add, ast.Sub, ast.Mult, ast.Pow, ast.USub, ast.UAdd, ast.Not,
                         ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
        if func.returns or any(arg.annotation for arg in args.args):
            raise ValueError("annotations are not part of this task")
        if any(not isinstance(node, allowed_nodes) for node in ast.walk(tree)):
            raise ValueError("code contains a node outside the permitted expression language")
        cases = []
        for case in payload["cases"]:
            scope = dict(zip(payload["parameters"], case["args"]))
            actual = expression(func.body[0].value, scope, [10000])
            cases.append({**case, "actual": actual, "correct": exact_equal(actual, case["expected"])})
        result = {"correct": all(case["correct"] for case in cases), "cases": cases,
                  "method": "bounded_ast_interpreter_subprocess_no_exec_eval"}
    except Exception as error:
        result = {"correct": False, "error": f"{type(error).__name__}: {error}",
                  "method": "bounded_ast_interpreter_subprocess_no_exec_eval"}
    print(json.dumps(result))
    return 0


def check_answer(task, content):
    if task["kind"] == "code":
        payload = {key: task[key] for key in ("function", "parameters", "cases")}
        payload["code"] = content
        try:
            worker = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()), "--code-worker"],
                                    input=json.dumps(payload), text=True, capture_output=True,
                                    timeout=4, cwd=tempfile.gettempdir(), env={"PATH": os.defpath})
            if worker.returncode != 0:
                return {"correct": False, "error": "code checker exited abnormally", "stderr": worker.stderr}
            return json.loads(worker.stdout)
        except (subprocess.TimeoutExpired, ValueError) as error:
            return {"correct": False, "error": str(error), "method": "bounded_ast_interpreter_subprocess_no_exec_eval"}
    def reject_constant(value):
        raise ValueError("nonstandard JSON constant: " + value)

    try:
        actual = json.loads(unfence(content), parse_constant=reject_constant)
    except ValueError as error:
        return {"correct": False, "expected": task["expected"], "error": str(error)}
    return {"correct": exact_equal(actual, task["expected"]), "actual": actual, "expected": task["expected"],
            "method": "exact_typed_json_equality"}


def long_task(scenario, budget, nonce, model, args, counter, document):
    target = budget - args.max_tokens - 8
    if budget > counter.context:
        raise BenchError(f"requested {budget}-token tier exceeds active context {counter.context}")
    if target < 128:
        raise BenchError("long-input budget leaves insufficient prompt space")
    keys = ["BEGIN_" + nonce[:8], "MIDDLE_" + nonce[:8], "END_" + nonce[:8]]
    expected = {key: digest(nonce + key)[:16] for key in keys}
    facts = [f"\nAUTHORITATIVE RECORD {key} = {expected[key]}\n" for key in keys]
    source = document or "".join(
        f"Archive entry {index:05d}: station {digest(nonce + str(index))[:12]}; measured quantity {(index * 37) % 997}; this is an unrelated historical record.\n"
        for index in range(2048))

    def build(characters):
        text = (source * (characters // len(source) + 1))[:characters]
        middle = len(text) // 2
        prompt = (f"Benchmark case {nonce}. Read the document and retrieve records, ignoring unrelated entries.\n"
                  "<document>" + facts[0] + text[:middle] + facts[1] + text[middle:] + facts[2] +
                  "</document>\nReturn only a JSON object mapping each of these three keys to its exact record value: " +
                  ", ".join(keys) + ". No explanation or other keys.")
        return prompt

    # Binary search on the full rendered prompt, never byte/character slicing a fact.
    low, high = 0, target * 8
    prompt = build(0)
    count = counter.count(request_body(model, prompt, args))
    guard = lambda info: info["tokens"] if info["exact"] else info["conservative_budget_tokens"]
    if guard(count) > target:
        raise BenchError("minimum long-input prompt exceeds the available budget")
    while low <= high:
        middle = (low + high) // 2
        candidate = build(middle)
        info = counter.count(request_body(model, candidate, args))
        if guard(info) <= target:
            prompt, count = candidate, info
            low = middle + 1
        else:
            high = middle - 1
    return {"id": f"{scenario}-{budget}", "scenario": scenario, "kind": "json", "prompt": prompt,
            "expected": expected, "requested_total_budget": budget, "target_prompt_tokens": target,
            "preflight_count": count, "fact_positions": ["beginning", "middle", "end"],
            "document_source_sha256": digest(source)}


def metrics(result):
    usage, timings = result.get("usage", {}), result.get("timings", {})
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", usage.get("cached_tokens"))
    if cached is None:
        cached = timings.get("cache_n")
    offered, accepted = timings.get("draft_n"), timings.get("draft_n_accepted")
    result["metrics"] = {
        "actual_prompt_tokens": usage.get("prompt_tokens"),
        "actual_completion_tokens": usage.get("completion_tokens"),
        "cached_prompt_tokens": cached,
        "prefill_uncached_tokens": timings.get("prompt_n"),
        "prefill_ms": timings.get("prompt_ms"),
        "prefill_uncached_tokens_per_second": timings.get("prompt_per_second"),
        "decode_tokens": timings.get("predicted_n"),
        "decode_ms": timings.get("predicted_ms"),
        "decode_tokens_per_second": timings.get("predicted_per_second"),
        "draft_tokens_offered": offered, "draft_tokens_accepted": accepted,
        "draft_acceptance": accepted / offered if isinstance(offered, (int, float)) and offered > 0 and isinstance(accepted, (int, float)) else None,
        "cache_status": "unknown" if cached is None else "cached_or_partially_cached" if cached else "uncached",
    }


def summarize(results):
    groups = {}
    for row in results:
        group = groups.setdefault(row["scenario"], {"requests": 0, "passed": 0, "failed": 0})
        group["requests"] += 1
        group["passed"] += bool(row.get("passed"))
        group["failed"] += not bool(row.get("passed"))
    for scenario, group in groups.items():
        rows = [row for row in results if row["scenario"] == scenario]
        for field in ("ttft_seconds", "total_seconds"):
            values = [row[field] for row in rows if row.get(field) is not None]
            group[field + "_median"] = statistics.median(values) if values else None
        for metric in ("decode_tokens_per_second", "prefill_uncached_tokens_per_second", "draft_acceptance"):
            values = [row["metrics"][metric] for row in rows if row.get("metrics", {}).get(metric) is not None]
            group[metric + "_median"] = statistics.median(values) if values else None
        group["cached_requests"] = sum(row.get("metrics", {}).get("cache_status") == "cached_or_partially_cached" for row in rows)
        group["unknown_cache_requests"] = sum(row.get("metrics", {}).get("cache_status") == "unknown" for row in rows)
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.environ.get("MAYA_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--model", default=os.environ.get("MAYA_MODEL_ID", ""))
    parser.add_argument("--key", default=os.environ.get("MAYA_API_KEY", ""), help="prefer MAYA_API_KEY to avoid shell history exposure")
    parser.add_argument("--label", default="maya")
    parser.add_argument("--output", required=True, help="private JSON evidence path outside this checkout")
    parser.add_argument("--scenarios", default="japanese,code,long-input", help="comma-separated japanese,code,long-input,retrieval")
    parser.add_argument("--long-input-sizes", type=size_list, default=size_list("8k"), help="total budgets, including output/slack; default 8k")
    parser.add_argument("--retrieval-sizes", type=size_list, default=size_list("32k,64k,128k"), help="total context tiers; oversized tiers fail without a generation request")
    parser.add_argument("--context-size", type=token_size, help="optional active context cap; never overrides a smaller discovered cap")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--timeout", type=float, default=1800, help="socket inactivity timeout and event-checked request deadline, seconds")
    parser.add_argument("--reasoning-effort", choices=("none", "low", "high", "max"), default="none")
    parser.add_argument("--document-file", type=Path, help="optional UTF-8 filler document; facts are inserted by the helper")
    parser.add_argument("--maya-root", type=Path, help="trusted pinned upstream checkout for local exact token counting")
    parser.add_argument("--tokenizer-dir", type=Path, help="upstream tokenizer directory including chat_template.jinja")
    args = parser.parse_args()
    scenarios = args.scenarios.split(",")
    if not scenarios or any(scenario not in ("japanese", "code", "long-input", "retrieval") for scenario in scenarios):
        parser.error("unknown scenario")
    if args.repeat < 1 or args.max_tokens < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("repeat, max-tokens, and timeout must be positive")
    output = Path(args.output).expanduser().resolve()
    root = Path(__file__).resolve().parents[1]
    if output == root or root in output.parents:
        parser.error("--output must be outside the checkout (private logs must not be tracked)")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "label": args.label, "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "settings": {"model": args.model, "seed": args.seed, "repeat": args.repeat,
                           "max_tokens": args.max_tokens, "reasoning_effort": args.reasoning_effort,
                           "scenarios": scenarios, "long_input_sizes": args.long_input_sizes,
                           "retrieval_sizes": args.retrieval_sizes, "parallel": 1},
              "measurement_notes": [
                  "TTFT begins before HTTP submission and ends at first nonempty reasoning_content or content delta; empty role chunks and heartbeats do not count.",
                  "TTFT is observable generated text, not the engine's first internal token: UTF-8 assembly and upstream tag parsing can delay it. No response_format is requested because upstream JSON mode buffers content.",
                  "End-to-end includes upload, queueing, prefill, decode, network and stream parsing. HTTP timeout is inactivity-based; overall deadline is checked between stream lines.",
                  "Prefill rates are engine uncached prompt_n/prompt_ms, never total prompt_tokens/TTFT. Cache counts are retained; nonce variation discourages but cannot guarantee no cache reuse.",
                  "Decode rate is the server engine clock; OpenAI completion tokens may differ from the engine denominator when stop/parser tokens are involved.",
                  "Synthetic retrieval checks three exact values at beginning/middle/end, not general long-context comprehension or all possible positions.",
                  "Code correctness covers the constrained expression tasks and listed functional cases only. A bounded AST interpreter runs in an isolated Python subprocess with a 4-second timeout; no generated Python is executed, and this is not a general Python sandbox.",
                  "Approximate fallback uses UTF-8 bytes/4 plus estimated template tokens, with a conservative byte-BPE/template budget reserve; it cannot establish exact near-capacity occupancy. API usage remains the actual prompt count.",
              ], "results": [], "summary": {}}
    save_report(output, report)
    try:
        client = Client(args.base_url, args.key, args.timeout)
        report["base_url"] = client.base
        health = client.json("/health")
        report["health"] = health
        if health.get("status") != "ok":
            raise BenchError("service health status is not ok")
        models = client.json("/v1/models")
        report["models"] = models
        model = args.model or next((entry.get("id") for entry in models.get("data", []) if entry.get("id")), None)
        if not model:
            raise BenchError("no loaded model discovered")
        report["settings"]["model"] = model
        probe = request_body(model, "Token budget probe.", args)
        counter = Counter(client, args, probe)
        report["token_counter"] = {"source": counter.source, "context_size": counter.context,
                                   "warning": counter.warning}
        document = args.document_file.read_text(encoding="utf-8") if args.document_file else None
        if document == "":
            raise BenchError("document file must not be empty")
        for repetition in range(args.repeat):
            specs = [task for task in fixed_tasks() if task["scenario"] in scenarios]
            for scenario, sizes in (("long-input", args.long_input_sizes), ("retrieval", args.retrieval_sizes)):
                if scenario in scenarios:
                    specs.extend({"id": f"{scenario}-{size}", "scenario": scenario, "budget": size} for size in sizes)
            for index, spec in enumerate(specs):
                nonce = digest(f"maya-bench:{args.seed}:{repetition}:{index}:{spec['id']}")[:24]
                result = {"id": spec["id"], "scenario": spec["scenario"], "repetition": repetition + 1,
                          "nonce": nonce, "passed": False}
                report["results"].append(result)
                try:
                    if "budget" in spec:
                        task = long_task(spec["scenario"], spec["budget"], nonce, model, args, counter, document)
                    else:
                        task = {**spec, "prompt": f"Benchmark case {nonce}.\n" + spec["prompt"]}
                    body = request_body(model, task["prompt"], args)
                    result["request"] = body
                    result["prompt_sha256"] = digest(task["prompt"])
                    result["task"] = {key: value for key, value in task.items() if key != "prompt"}
                    count = task.get("preflight_count") or counter.count(body)
                    result["preflight_count"] = count
                    budget_count = count["tokens"] if count["exact"] else count["conservative_budget_tokens"]
                    if budget_count + args.max_tokens + 8 > counter.context:
                        raise BenchError("prompt plus output and engine slack exceeds active context")
                    # Persist the exact request before potentially failing mid-stream.
                    save_report(output, report)
                    client.stream(body, result)
                    metrics(result)
                    result["answer_check"] = check_answer(task, result["content"])
                    failures = []
                    if not result["answer_check"]["correct"]:
                        failures.append("answer correctness failed")
                    if result["finish_reason"] != "stop":
                        failures.append("finish_reason is not stop")
                    if not result["stream_done"]:
                        failures.append("missing SSE [DONE]")
                    if result["ttft_seconds"] is None:
                        failures.append("no generated content or reasoning delta")
                    if not isinstance(result["usage"].get("prompt_tokens"), int) or not isinstance(result["usage"].get("completion_tokens"), int):
                        failures.append("missing actual OpenAI token usage")
                    if not all(key in result["timings"] for key in ("prompt_n", "prompt_ms", "predicted_n", "predicted_ms")):
                        failures.append("missing final Maya engine timings")
                    actual = result["usage"].get("prompt_tokens")
                    if isinstance(actual, int) and actual + args.max_tokens + 8 > counter.context:
                        failures.append("actual prompt exceeds reserved context budget")
                    if count["exact"] and actual != count["tokens"]:
                        failures.append("preflight exact count differs from API usage")
                    result["failures"] = failures
                    result["passed"] = not failures
                except (BenchError, OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
                    result["error"] = f"{type(error).__name__}: {error}"
                    metrics(result)
                report["summary"] = summarize(report["results"])
                save_report(output, report)
                print(f"{result['id']} repeat={repetition + 1} {'PASS' if result['passed'] else 'FAIL'} "
                      f"ttft={result.get('ttft_seconds')} total={result.get('total_seconds')} "
                      f"decode_tps={result.get('metrics', {}).get('decode_tokens_per_second')}", flush=True)
    except (BenchError, OSError, ValueError, TypeError, KeyError, ImportError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    except KeyboardInterrupt:
        report["error"] = "interrupted by operator; partial evidence retained"
    finally:
        report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        report["summary"] = summarize(report["results"])
        report["passed"] = bool(report["results"]) and not report.get("error") and all(row["passed"] for row in report["results"])
        save_report(output, report)
    print(json.dumps({"passed": report["passed"], "summary": report["summary"], "output": str(output)}, ensure_ascii=False))
    if report.get("error"):
        print(report["error"], file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--code-worker"]:
        sys.exit(code_worker())
    sys.exit(main())
