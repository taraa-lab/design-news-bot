"""test_gemini.py — check which Google endpoint accepts GEMINI_API_KEY and how good the Persian is.
Never prints the key. Writes data/gemini_test.json."""
import os, json, requests
from datetime import datetime, timezone
from collector import Article
import summarizer as S

KEY = os.environ["GEMINI_API_KEY"]
arts = [
    Article(title="Dyson unveils ergonomic vacuum designed with Studio Aria", url="u1", source="Dezeen",
            summary="Dyson has launched a lightweight vacuum cleaner developed with London-based Studio Aria. The handle is made from recycled aluminium."),
    Article(title="Red Dot Award 2027 opens for entries in product design", url="u2", source="Designboom",
            summary="Registration for the Red Dot Award: Product Design 2027 is open until 15 January 2027. Products launched since 2025 are eligible."),
    Article(title="Milan Design Week: Muji shows modular wooden furniture", url="u3", source="Wallpaper",
            summary="Muji presented a modular furniture system made from Japanese cedar at Milan Design Week."),
]
msg = S._build_user_message(arts)
body = {"systemInstruction": {"parts": [{"text": S.SYSTEM_PROMPT_FA}]},
        "contents": [{"role": "user", "parts": [{"text": msg}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096, "responseMimeType": "application/json"}}
out = {"at": datetime.now(timezone.utc).isoformat(), "key_prefix": KEY[:3], "studio": {}, "vertex": {}}


def attempt(kind, model):
    if kind == "studio":
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          headers={"x-goog-api-key": KEY, "Content-Type": "application/json"}, json=body, timeout=90)
    else:
        r = requests.post(f"https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent",
                          params={"key": KEY}, headers={"Content-Type": "application/json"}, json=body, timeout=90)
    res = {"status": r.status_code}
    if r.status_code == 200:
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
            items = S._parse_results("".join(p.get("text", "") for p in parts))
            res["items"] = len(items)
            res["valid_persian"] = sum(1 for i in items if S._quality_ok(i, "fa"))
            res["sample"] = [{"title": i.get("title_fa"), "summary": i.get("summary"), "category": i.get("category"),
                              "importance": i.get("importance")} for i in items]
        except Exception as e:
            res["parse_error"] = str(e)[:150]
    else:
        res["error"] = r.text[:220].replace(KEY, "<key>")
    return res


for kind in ("studio", "vertex"):
    for model in ("gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash"):
        try:
            out[kind][model] = attempt(kind, model)
        except Exception as e:
            out[kind][model] = {"exception": str(e)[:150].replace(KEY, "<key>")}
        print(kind, model, out[kind][model].get("status"), out[kind][model].get("valid_persian"))

os.makedirs("../data", exist_ok=True)
json.dump(out, open("../data/gemini_test.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
