"""
user_store.py — Save and load per-user settings in a JSON file on GitHub.
Schema per user:
  {
    "lang": "fa" | "en",
    "interests": ["automotive","product","furniture","jewelry","accessory","service"],
    "active": true
  }
"""
import os, json, base64, logging, requests

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN","")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "taraa-lab/design-news-bot")
USERS_PATH   = "data/users.json"
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

_cache: dict = {}
_cache_sha: str = ""

def _gh_get():
    global _cache, _cache_sha
    r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{USERS_PATH}", headers=HEADERS)
    if r.status_code == 404:
        return {}, ""
    d = r.json()
    content = base64.b64decode(d["content"].replace("\n","")).decode("utf-8")
    _cache = json.loads(content)
    _cache_sha = d["sha"]
    return _cache, _cache_sha

def _gh_put(data: dict, sha: str):
    encoded = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode()).decode()
    payload = {"message": "update: user preferences", "content": encoded}
    if sha:
        payload["sha"] = sha
    r = requests.put(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{USERS_PATH}",
                     headers=HEADERS, json=payload)
    return r.status_code in (200, 201)

def get_user(user_id: int) -> dict:
    users, _ = _gh_get()
    return users.get(str(user_id), {"lang":"fa","interests":["all"],"active":True})

def save_user(user_id: int, data: dict):
    users, sha = _gh_get()
    users[str(user_id)] = data
    _gh_put(users, sha)

def get_all_users() -> dict:
    users, _ = _gh_get()
    return users
