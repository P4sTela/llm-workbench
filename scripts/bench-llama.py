#!/usr/bin/env python3
"""Minimal benchmark for an OpenAI-compatible llama.cpp server.

Measures: prefill t/s on a ~2K-token prompt, decode t/s over three 256-token
generations (thinking off), and verifies an OpenAI tool call round trip.
Prints one JSON object to stdout and appends it to results.jsonl when
--out is given.
"""
import argparse
import json
import statistics
import time
import urllib.request

FILLER = (
    "The PCIe link between a host and a GPU is described by its generation and "
    "lane width; each generation doubles the per-lane transfer rate, and the "
    "effective bandwidth is the product of the two. "
)


def post(url, body, timeout=600):
    req = urllib.request.Request(
        url, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://100.0.0.83:8081")
    ap.add_argument("--model", default="qwen3.8-27b-base")
    ap.add_argument("--out")
    args = ap.parse_args()
    url = args.base.rstrip("/") + "/v1/chat/completions"

    # prefill: ~2K tokens of context
    long_prompt = FILLER * 60
    r = post(url, {
        "model": args.model,
        "messages": [{"role": "user", "content": long_prompt + "\n\nSummarise in one sentence."}],
        "max_tokens": 32,
        "chat_template_kwargs": {"enable_thinking": False},
    })
    t = r.get("timings", {})
    prefill = {"prompt_n": t.get("prompt_n"), "tps": t.get("prompt_per_second")}

    # decode: three short generations
    dec = []
    for _ in range(3):
        r = post(url, {
            "model": args.model,
            "messages": [{"role": "user", "content": "Explain KV cache offloading in two sentences."}],
            "max_tokens": 256,
            "chat_template_kwargs": {"enable_thinking": False},
        })
        t = r.get("timings", {})
        dec.append({"tps": t.get("predicted_per_second"), "n": t.get("predicted_n")})

    # tool call
    tool_ok, tool_name = False, None
    r = post(url, {
        "model": args.model,
        "messages": [{"role": "user", "content": "Call report_status now with state=ok. Do not reply with prose."}],
        "tools": [{"type": "function", "function": {
            "name": "report_status",
            "description": "Report a status.",
            "parameters": {"type": "object", "properties": {"state": {"type": "string"}},
                           "required": ["state"], "additionalProperties": False}}}],
        "max_tokens": 200,
        "chat_template_kwargs": {"enable_thinking": False},
    })
    ch = r["choices"][0]
    if ch.get("finish_reason") == "tool_calls":
        calls = ch["message"].get("tool_calls") or []
        tool_name = calls[0]["function"]["name"] if calls else None
        tool_ok = tool_name == "report_status"

    res = {
        "model": args.model,
        "base": args.base,
        "prefill": prefill,
        "decode_tps": [round(d["tps"], 1) for d in dec],
        "decode_median": round(statistics.median([d["tps"] for d in dec]), 1),
        "decode_tokens": [d["n"] for d in dec],
        "tool_call_ok": tool_ok,
        "tool_name": tool_name,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    print(json.dumps(res, ensure_ascii=False))
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
