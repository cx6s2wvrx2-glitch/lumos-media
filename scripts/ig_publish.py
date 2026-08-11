#!/usr/bin/env python3
"""
Instagram publisher — single account per repo.
Reads posts/queue.json, publishes anything due, marks it published.
Idempotent: a post with published_at is never touched again, and posts
older than 24h are skipped so a re-run can't back-fill stale content.

Env (from GitHub secrets):
  IG_TOKEN            long-lived token (shared across both accounts)
  IG_USERID           the Instagram user id THIS repo publishes to
"""
import json, os, sys, time, datetime, urllib.request, urllib.parse, urllib.error

QUEUE = "posts/queue.json"
API   = "https://graph.facebook.com/v21.0"
TOKEN = os.environ["IG_TOKEN"]
UID   = os.environ["IG_USERID"]

def _req(method, path, data=None):
    url = f"{API}/{path}"
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code}: {e.read().decode()[:300]}")

def wait_ready(cid):
    for _ in range(30):
        r = _req("GET", f"{cid}?fields=status_code&access_token={TOKEN}")
        if r.get("status_code") == "FINISHED":
            return
        if r.get("status_code") == "ERROR":
            raise RuntimeError(f"container {cid} errored")
        time.sleep(10)
    raise RuntimeError(f"container {cid} timed out")

def make_container(item, is_child=False):
    d = {"access_token": TOKEN}
    if item["type"] == "reel":
        d.update(media_type="REELS", video_url=item["url"])
    else:
        d["image_url"] = item["url"]
    if is_child:
        d["is_carousel_item"] = "true"
    else:
        d["caption"] = item.get("caption", "")
    return _req("POST", f"{UID}/media", d)["id"]

def publish(post):
    if post["type"] == "carousel":
        kids = []
        for u in post["urls"]:
            k = make_container({"type": "image", "url": u}, is_child=True)
            wait_ready(k); kids.append(k)
        cid = _req("POST", f"{UID}/media", {
            "media_type": "CAROUSEL", "children": ",".join(kids),
            "caption": post.get("caption", ""), "access_token": TOKEN})["id"]
    else:
        cid = make_container({"type": post["type"], "url": post["url"],
                              "caption": post.get("caption", "")})
    wait_ready(cid)
    return _req("POST", f"{UID}/media_publish",
                {"creation_id": cid, "access_token": TOKEN})["id"]

def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    queue = json.load(open(QUEUE, encoding="utf-8"))
    done = fail = 0
    for p in queue:
        if p.get("published_at"):
            continue
        due = datetime.datetime.fromisoformat(p["scheduled_at"])
        if due > now or (now - due).total_seconds() > 86400:
            continue
        try:
            p["ig_id"] = publish(p)
            p["published_at"] = now.isoformat()
            done += 1
            print("published", p["id"], "->", p["ig_id"])
        except Exception as e:
            p["error"] = str(e)[:300]; fail += 1
            print("FAILED", p["id"], e, file=sys.stderr)
    if done or fail:
        json.dump(queue, open(QUEUE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print(f"done: {done} published, {fail} failed")
    sys.exit(1 if fail else 0)

if __name__ == "__main__":
    main()
