"""Minimal Anthropic API smoke test (M0).

Checks, per configured model: the model ID exists (models.list), a structured-output
call returns schema-valid JSON, and a tool-use round trip completes. Prints token usage.

Usage: python scripts/api_smoke_test.py [--models id1,id2]
Credentials come from the environment (ANTHROPIC_API_KEY); nothing is read from files.
Sampling parameters (temperature/top_p/top_k) are deliberately not sent: the API rejects them.
"""
import argparse
import json
import sys

import anthropic

DEFAULT_MODELS = "claude-haiku-5-5,claude-sonnet-5-5,claude-opus-5-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "authorizes_deletion": {"type": "boolean"},
        "language": {"type": "string"},
    },
    "required": ["authorizes_deletion", "language"],
    "additionalProperties": False,
}

TOOL = {
    "name": "lookup_resource",
    "description": "Look up a resource by id and return its status.",
    "input_schema": {
        "type": "object",
        "properties": {"resource_id": {"type": "string"}},
        "required": ["resource_id"],
        "additionalProperties": False,
    },
    "strict": True,
}


def usage_of(resp):
    u = resp.usage
    return {"in": u.input_tokens, "out": u.output_tokens}


def structured_check(client, model):
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": "Classify this customer message. Message: 'Quiero que eliminen mi cuenta.'",
        }],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    assert set(data) == {"authorizes_deletion", "language"}, data
    return data, usage_of(resp)


def tool_check(client, model):
    messages = [{
        "role": "user",
        "content": "Use the lookup_resource tool to check resource account_001, then state its status.",
    }]
    used = {"in": 0, "out": 0}
    resp = client.messages.create(model=model, max_tokens=2000, tools=[TOOL], messages=messages)
    for k, v in usage_of(resp).items():
        used[k] += v
    if resp.stop_reason != "tool_use":
        raise AssertionError(f"expected tool_use, got {resp.stop_reason}")
    messages.append({"role": "assistant", "content": resp.content})
    results = []
    for block in resp.content:
        if block.type == "tool_use":
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps({"resource_id": block.input["resource_id"], "status": "NOT_FOUND"}),
            })
    messages.append({"role": "user", "content": results})
    resp2 = client.messages.create(model=model, max_tokens=2000, tools=[TOOL], messages=messages)
    for k, v in usage_of(resp2).items():
        used[k] += v
    final = " ".join(b.text for b in resp2.content if b.type == "text")
    return final[:120], used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=DEFAULT_MODELS)
    args = ap.parse_args()
    client = anthropic.Anthropic()
    print("anthropic SDK", anthropic.__version__)
    available = {m.id for m in client.models.list()}
    failures = 0
    for model in args.models.split(","):
        print(f"\n== {model}")
        if model not in available:
            print("  models.list: NOT FOUND")
            failures += 1
            continue
        print("  models.list: found")
        for name, fn in (("structured", structured_check), ("tool_use", tool_check)):
            try:
                out, used = fn(client, model)
                print(f"  {name}: OK {out} tokens={used}")
            except Exception as e:  # report every failure, do not hide
                failures += 1
                print(f"  {name}: FAIL {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
