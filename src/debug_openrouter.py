"""debug_openrouter.py — check key validity and list current free models."""
import os, json, requests

api_key = os.environ.get("OPENROUTER_API_KEY", "")
report = {"key_present": bool(api_key), "key_length": len(api_key)}

# Check key validity
try:
    r = requests.get("https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {api_key}"}, timeout=20)
    report["key_check_status"] = r.status_code
    report["key_check_body"] = r.text[:500]
except Exception as e:
    report["key_check_error"] = str(e)

# List free models
try:
    r2 = requests.get("https://openrouter.ai/api/v1/models", timeout=20)
    models = r2.json().get("data", [])
    free_models = [m["id"] for m in models if m.get("pricing",{}).get("prompt") == "0"]
    report["free_models_count"] = len(free_models)
    report["free_models"] = free_models[:30]
except Exception as e:
    report["models_error"] = str(e)

# Try an actual chat completion with a modern free model candidate
test_models = [
    "meta-llama/llama-3.1-8b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "qwen/qwen-2.5-7b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]
report["test_calls"] = {}
for model in test_models:
    try:
        r3 = requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role":"user","content":"Say OK"}]},
            timeout=20)
        report["test_calls"][model] = {"status": r3.status_code, "body": r3.text[:300]}
    except Exception as e:
        report["test_calls"][model] = {"error": str(e)}

with open("../openrouter_debug.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
