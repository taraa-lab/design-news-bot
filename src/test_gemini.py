"""test_gemini.py v2 — exercises the REAL summarizer Gemini path. Never prints the key."""
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
out = {"at": datetime.now(timezone.utc).isoformat()}
try:
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 200},
                     headers={"x-goog-api-key": KEY}, timeout=20)
    out["list_status"] = r.status_code
    out["models_generateContent"] = sorted(str(m.get("name", "")).replace("models/", "") for m in r.json().get("models", [])
                                           if "generateContent" in (m.get("supportedGenerationMethods") or []))
except Exception as e:
    out["list_error"] = str(e)[:150].replace(KEY, "<key>")
out["chosen"] = S._gemini_models()
res = S._gemini_batch(S._build_user_message(arts), "fa")
out["batch"] = {"items": len(res), "valid_persian": sum(1 for i in res if S._quality_ok(i, "fa")),
                "last_good": S._gem["last_good"], "dead": sorted(S._gem["dead"]),
                "sample": [{"title": i.get("title_fa"), "summary": i.get("summary"), "category": i.get("category"), "importance": i.get("importance")} for i in res]}
print("chosen:", out["chosen"], "| items:", out["batch"]["items"], "| valid:", out["batch"]["valid_persian"], "| model:", out["batch"]["last_good"])
os.makedirs("../data", exist_ok=True)
json.dump(out, open("../data/gemini_test.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
