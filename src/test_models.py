"""test_models.py — test candidate free models with a realistic Persian JSON task."""
import os, json, requests

api_key = os.environ.get("OPENROUTER_API_KEY", "")
candidates = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-20b:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
]

prompt = """Article: "Samsung Wins Red Dot Award for New OLED TV Design"
Return ONLY a JSON array with one object: {"title_fa": "Persian translation", "summary": "3-sentence Persian summary", "category": "جوایز طراحی", "importance": "بالا"}"""

results = {}
for model in candidates:
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role":"user","content":prompt}], "max_tokens": 500},
            timeout=30)
        body = r.json()
        text = body.get("choices",[{}])[0].get("message",{}).get("content","")
        results[model] = {"status": r.status_code, "content": text[:400]}
    except Exception as e:
        results[model] = {"error": str(e)}

with open("model_test_results.json","w",encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(json.dumps(results, ensure_ascii=False, indent=2))
