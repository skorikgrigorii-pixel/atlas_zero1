from dotenv import load_dotenv
load_dotenv(override=True)

import json, os, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

from src.az_enterprise.core.cloudflare_r2_staging_rc1 import CloudflareR2StagingRC1
from src.az_enterprise.core.tiktok_connector_rc1 import TikTokConnectorRC1

GRAPH = "https://graph.facebook.com/v23.0"
MASTER = Path(r"workspace\exports\amazonia\rc2\promotion\masters\amazonia__promo_00677125_00709188.mp4").resolve()
CAPTION = "Deep inside the Amazon, history, danger and mystery still hide beneath the world's largest rainforest. #Amazon #Amazonia #Documentary #History #AtlasZero"

token = os.environ["INSTAGRAM_ACCESS_TOKEN"]

def graph(method, path, params=None):
    p = dict(params or {})
    p["access_token"] = token
    encoded = urllib.parse.urlencode(p)
    url = GRAPH + "/" + path.lstrip("/")
    data = None
    if method == "GET":
        url += "?" + encoded
    else:
        data = encoded.encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GRAPH {path}: HTTP {e.code}: {body}") from e

# Discover usable Instagram professional account.
candidates = []
env_id = os.getenv("INSTAGRAM_USER_ID", "").strip()
if env_id:
    candidates.append(env_id)

accounts = graph("GET", "me/accounts", {"fields":"id,name,instagram_business_account"}).get("data", [])
for x in accounts:
    ig = x.get("instagram_business_account") or {}
    if ig.get("id"):
        candidates.append(str(ig["id"]))

businesses = graph("GET", "me/businesses", {"fields":"id,name"}).get("data", [])
for b in businesses:
    for edge in ("owned_instagram_accounts", "client_instagram_accounts"):
        try:
            rows = graph("GET", f"{b['id']}/{edge}", {"fields":"id,username"}).get("data", [])
            candidates.extend(str(x["id"]) for x in rows if x.get("id"))
        except Exception:
            pass

seen = set()
ig_id = None
for cid in candidates:
    if cid in seen:
        continue
    seen.add(cid)
    try:
        p = graph("GET", cid, {"fields":"id,username,account_type,media_count"})
        if p.get("id"):
            ig_id = str(p["id"])
            print("INSTAGRAM ACCOUNT:", p.get("username"), ig_id)
            break
    except Exception:
        pass

if not ig_id:
    raise RuntimeError("No Instagram professional account accessible by current Facebook token")

if not MASTER.is_file():
    raise FileNotFoundError(MASTER)

# Stage once to public R2 URL.
staging = CloudflareR2StagingRC1.from_env_file(".env")
staged = staging.stage(MASTER)

try:
    # Instagram Reel container.
    c = graph("POST", f"{ig_id}/media", {
        "media_type":"REELS",
        "video_url":staged.public_url,
        "caption":CAPTION,
        "share_to_feed":"true",
    })
    container_id = str(c["id"])
    print("INSTAGRAM CONTAINER:", container_id)

    for _ in range(36):
        st = graph("GET", container_id, {"fields":"status_code,status"})
        code = str(st.get("status_code","")).upper()
        print("INSTAGRAM STATUS:", code)
        if code == "FINISHED":
            break
        if code in ("ERROR","EXPIRED"):
            raise RuntimeError(str(st))
        time.sleep(5)
    else:
        raise TimeoutError("Instagram container timeout")

    pub = graph("POST", f"{ig_id}/media_publish", {"creation_id":container_id})
    print("INSTAGRAM: PUBLISHED", pub.get("id"))

finally:
    staging.cleanup(staged)

# TikTok: same master.
tt = TikTokConnectorRC1()
creator = tt.creator_info().get("data", {})
options = creator.get("privacy_level_options") or []

privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in options else "SELF_ONLY"

init = tt.init_direct_post(
    video_path=MASTER,
    title=CAPTION,
    privacy_level=privacy,
    disable_comment=False,
    disable_duet=False,
    disable_stitch=False,
)

data = init.get("data") or {}
upload_url = data["upload_url"]
publish_id = data["publish_id"]

print("TIKTOK UPLOAD HTTP:", tt.upload_video(upload_url=upload_url, video_path=MASTER))

for _ in range(36):
    st = tt.publish_status(publish_id)
    d = st.get("data") or {}
    status = str(d.get("status","")).upper()
    print("TIKTOK STATUS:", status)
    if status in ("PUBLISH_COMPLETE","PUBLISHED"):
        print("TIKTOK: PUBLISHED", publish_id, "PRIVACY:", privacy)
        break
    if status in ("FAILED","PUBLISH_FAILED"):
        raise RuntimeError(json.dumps(st, ensure_ascii=False))
    time.sleep(5)
else:
    raise TimeoutError("TikTok publication timeout")

print("INSTAGRAM + TIKTOK: COMPLETE")
