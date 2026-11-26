"""
Avtomatik YouTube video generatori (ispan tilida tarixiy kontent).
"""
import asyncio
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import edge_tts
import requests

MODE = os.environ.get("MODE", "short").strip()
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
PRIVACY = os.environ.get("PRIVACY", "private")

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
VOICE = os.environ.get("TTS_VOICE", "es-MX-JorgeNeural")
RATE = "+8%" if MODE == "short" else "+0%"

W, H = (1080, 1920) if MODE == "short" else (1920, 1080)
FPS = 25

ROOT = Path(__file__).parent
WORK = ROOT / "work"
OUT = ROOT / "output"
USED_FILE = ROOT / "used_topics.json"
MUSIC = ROOT / "music.mp3"
CLIPS_DIR = ROOT / "clips"
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")

WIKI_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "yt-auto-history/1.0 (educational personal project)"}


def log(*a):
    print(*a, flush=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log("XATO buyruq:", " ".join(map(str, cmd))[:300])
        log(r.stderr[-1500:])
        raise RuntimeError("ffmpeg/ffprobe xatosi")
    return r.stdout


def load_used():
    if USED_FILE.exists():
        try:
            return json.loads(USED_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_used(used, topic):
    used.append({"topic": topic, "mode": MODE, "date": time.strftime("%Y-%m-%d")})
    USED_FILE.write_text(json.dumps(used, ensure_ascii=False, indent=1), encoding="utf-8")


def gemini_json(prompt):
    models = [GEMINI_MODEL, "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash", "gemini-2.5-flash"]
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    last = None
    for round_no in range(3):
        for m in dict.fromkeys(models):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
            try:
                r = requests.post(url, params={"key": GEMINI_KEY}, json=body, timeout=180)
                if r.status_code != 200:
                    log(f"Gemini {m} -> HTTP {r.status_code}: {r.text[:300]}")
                    last = RuntimeError(f"{m}: HTTP {r.status_code}")
                    continue
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                log(f"Gemini ishladi: {m}")
                return json.loads(text)
            except Exception as e:
                last = e
                log(f"Gemini {m} xato: {e}")
        time.sleep(20)
    raise RuntimeError(f"Gemini javob bermadi: {last}")


def make_script(used):
    recent = [u["topic"] for u in used[-80:]]
    if MODE == "short":
        spec = (
            "VIDEO TURI: YouTube Shorts (vertikal), taxminan 40-50 soniya.\n"
            "- Aynan 8 ta sahna. Hammasi birga 100-120 so'z.\n"
            "- Birinchi sahna: 2 soniyalik kuchli 'ilmoq' (savol yoki kutilmagan fakt).\n"
            "- Har bir sahna 1-2 qisqa gap. Oxirgi sahna: kutilmagan xulosa yoki savol."
        )
    else:
        spec = (
            "VIDEO TURI: uzun YouTube video, taxminan 7-9 daqiqa.\n"
            "- Aynan 12 ta sahna, har biri 80-100 so'z (jami ~1000 so'z).\n"
            "- Tuzilma: ilmoq, kirish, 3-4 asosiy bo'lim, xulosa. Hikoya ohangi, hujjatli film kabi.\n"
            "- Oxirida tomoshabinni obuna bo'lishga bir jumla bilan chaqiring."
        )
    prompt = f"""Sen ispan tilidagi tarixiy hujjatli videolar muallifisan. Auditoriya: Ispaniya va Lotin Amerikasi.
Mavzu doirasi: jahon tarixi (Qadimgi Rim va Yunoniston, Konkistadorlar, Azteklar va Inklar, Reconquista,
Napoleon, Ipak yo'li, O'rta asr imperiyalari, Amir Temur va Samarqand, buyuk kashfiyotlar va h.k.).

{spec}

QOIDALAR:
- "narration" matni FAQAT ispan tilida, ravon og'zaki nutq. Raqamlar va sanalarni so'z bilan emas, oddiy yozing.
- Faqat yaxshi hujjatlashtirilgan, tekshirilgan faktlarni yoz. Ishonching komil bo'lmagan sana, raqam yoki
  iqtibosni UMUMAN yozma. To'qima iqtibos yozma.
- Mavzu avval ishlatilganlardan farq qilsin. Oxirgi mavzular: {json.dumps(recent, ensure_ascii=False)}
- "image_query": Wikimedia Commons'da tarixiy rasm topish uchun 2-4 so'zli aniq qidiruv (inglizcha yoki
  ispancha), masalan "Battle of Lepanto painting", "Tenochtitlan map", "Registan Samarkand".
  Har sahnada boshqa rasm kerak bo'lsin.
- "video_query": stok-video kutubxonasi uchun 2-3 so'zli INGLIZCHA umumiy qidiruv (aniq nom emas, manzara/vaziyat),
  masalan "desert caravan", "ancient ruins", "sailing ship ocean", "medieval castle", "burning torch", "old map".

Faqat quyidagi JSON'ni qaytar:
{{
 "topic": "qisqa mavzu nomi (ispancha)",
 "title": "YouTube sarlavhasi, ispancha, qiziqarli, 70 belgigacha",
 "description": "2-3 gaplik ispancha tavsif",
 "tags": ["8-12 ta ispancha teg"],
 "scenes": [ {{"narration": "...", "image_query": "...", "video_query": "..."}} ]
}}"""
    data = gemini_json(prompt)
    scenes = [s for s in data.get("scenes", []) if isinstance(s, dict) and s.get("narration")]
    if len(scenes) < 5:
        raise RuntimeError("Ssenariy juda qisqa chiqdi")
    data["scenes"] = scenes
    data["title"] = re.sub(r"[<>]", "", str(data.get("title", data.get("topic", "Historia")))).strip()
    return data


async def _tts(text, path):
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))


def make_audio(scenes):
    paths = []
    for i, s in enumerate(scenes):
        p = WORK / f"a{i}.mp3"
        for attempt in range(3):
            try:
                asyncio.run(_tts(s["narration"], p))
                if p.exists() and p.stat().st_size > 1000:
                    break
            except Exception as e:
                log(f"TTS xato (sahna {i}, urinish {attempt + 1}): {e}")
                time.sleep(3)
        else:
            raise RuntimeError(f"Ovoz yaratilmadi: sahna {i}")
        paths.append(p)
    return paths


def duration(path):    
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


def _clean(s):
    return re.sub(r"<[^>]+>", "", html.unescape(s or "")).strip()


def _license_ok(lic):
    l = lic.lower()
    return any(k in l for k in ("public domain", "cc0", "cc by", "cc-by", "pd"))


def wiki_get(url, params=None, timeout=60):
    """Wikimedia 429 bersa kutib, qayta uriniladi."""
    for attempt in range(6):
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.status_code in (429, 503):
            wait = r.headers.get("Retry-After", "")
            wait = int(wait) if wait.isdigit() else 5 * (2 ** attempt)
            log(f"Wikimedia {r.status_code}, {min(wait, 60)} soniya kutaman")
            time.sleep(min(wait, 60))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def commons_search(query, used_urls):
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 25,
        "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 1920,
    }
    try:
        r = wiki_get(WIKI_API, params=params, timeout=40)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
    except Exception as e:
        log("Commons qidiruv xatosi:", e)
        return None
    for p in sorted(pages.values(), key=lambda x: x.get("index", 999)):
        ii = (p.get("imageinfo") or [None])[0]
        if not ii or ii.get("mime") not in ("image/jpeg", "image/png"):
            continue
        if ii.get("width", 0) < 900 or ii.get("height", 0) < 600:
            continue
        meta = ii.get("extmetadata", {})
        lic = _clean(meta.get("LicenseShortName", {}).get("value", ""))
        if not _license_ok(lic):
            continue
        url = ii.get("thumburl") or ii.get("url")
        if not url or url in used_urls:
            continue
        artist = _clean(meta.get("Artist", {}).get("value", "")) or "Autor desconocido"
        credit = f"{artist[:80]} - {lic} - {ii.get('descriptionurl', '')}"
        return url, credit
    return None


def fetch_image(query, topic, idx, used_urls):
    words = query.split()
    attempts = [query, " ".join(words[:3]), " ".join(words[:2]), topic]
    for q in dict.fromkeys(a for a in attempts if a.strip()):
        found = commons_search(q, used_urls)
        time.sleep(3)
        if not found:
            continue
        url, credit = found
        try:
            r = wiki_get(url, timeout=60)
            r.raise_for_status()
            if len(r.content) < 20000:
                continue
            ext = ".png" if url.lower().endswith(".png") else ".jpg"
            path = WORK / f"img{idx}{ext}"
            path.write_bytes(r.content)
            used_urls.add(url)
            return path, credit
        except Exception as e:
            log("Rasm yuklash xatosi:", e)
    return None, None


def blank_image(path):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x15151f:s={W}x{H}", "-frames:v", "1", str(path)])
    return path


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _caption_chunks(text):
    """Matnni subtitr bo'laklariga bo'ladi (har bo'lak 2 qatorgacha)."""
    max_chars = 20 if MODE == "short" else 38
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]


def _motions(n):
    """Har xil kamera harakatlari (zoompan ifodalari). n = kadrlar soni."""
    return [
        ("1+0.28*on/%d" % n, "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),            # yaqinlashish
        ("1.28-0.28*on/%d" % n, "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),         # uzoqlashish
        ("1.25", "(iw-iw/zoom)*on/%d" % n, "ih/2-(ih/zoom/2)"),                  # chapdan o'ngga
        ("1.25", "(iw-iw/zoom)*(1-on/%d)" % n, "ih/2-(ih/zoom/2)"),              # o'ngdan chapga
        ("1+0.3*on/%d" % n, "0", "0"),                                           # yuqori-chapga yaqinlashish
        ("1.25", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/%d" % n),                  # yuqoridan pastga
    ]


def _finish(src, text, dur, idx):
    """Rang berish + donadorlik + subtitrlar + kirish/chiqish. Oxirgi yorliq: [v]."""
    grade = (f"[{src}]eq=contrast=1.08:saturation=0.9:gamma=0.97,"
             "curves=r='0/0 0.5/0.54 1/1':b='0/0 0.5/0.46 1/1',"
             "vignette=PI/5,noise=alls=7:allf=t")
    chunks = _caption_chunks(text) if text else []
    cap_dir = WORK / f"caps{idx}"
    cap_dir.mkdir(exist_ok=True)
    total_chars = sum(len(c) for c in chunks) or 1
    t0 = 0.0
    size = 70 if MODE == "short" else 48
    ypos = "h*0.68" if MODE == "short" else "h*0.80"
    for ci, c in enumerate(chunks):
        d = max(0.8, (dur - 0.4) * len(c) / total_chars)
        f = cap_dir / f"c{ci}.txt"
        f.write_text(c, encoding="utf-8")
        grade += (f",drawtext=fontfile={FONT}:textfile={f.resolve()}:fontsize={size}:fontcolor=white:"
                  f"borderw=4:bordercolor=black:box=1:boxcolor=black@0.35:boxborderw=14:line_spacing=8:"
                  f"x=(w-text_w)/2:y={ypos}:enable='between(t,{t0:.2f},{t0 + d:.2f})'")
        t0 += d
    grade += f",fade=t=in:st=0:d=0.25,fade=t=out:st={max(0.0, dur - 0.25):.2f}:d=0.25,format=yuv420p[v]"
    return grade


def make_video_clip(video, audio, dur, out, text="", idx=0):
    """Haqiqiy harakatlanuvchi video (Flow yoki Pexels) + ovoz + subtitr."""
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1[base];"
          + _finish("base", text, dur, idx))
    run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(video), "-i", str(audio),
        "-filter_complex", vf, "-map", "[v]", "-map", "1:a",
        "-af", "apad", "-t", f"{dur:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        str(out),
    ])


def local_clips():
    if not CLIPS_DIR.exists():
        return []
    return sorted(p for p in CLIPS_DIR.iterdir() if p.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"))


def pexels_video(query, idx, used_ids):
    """Pexels'dan bepul stok-video topadi. (yo'l, kredit) yoki (None, None)."""
    if not PEXELS_KEY or not query:
        return None, None
    params = {"query": query, "per_page": 15, "orientation": "portrait" if MODE == "short" else "landscape"}
    try:
        r = requests.get("https://api.pexels.com/videos/search", params=params,
                         headers={"Authorization": PEXELS_KEY}, timeout=40)
        r.raise_for_status()
        vids = r.json().get("videos", [])
    except Exception as e:
        log("Pexels qidiruv xatosi:", e)
        return None, None
    target = 1080
    for v in vids:
        if v["id"] in used_ids or v.get("duration", 0) < 4:
            continue
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")]
        if MODE == "short":
            files = [f for f in files if f["height"] >= f["width"]]
        else:
            files = [f for f in files if f["width"] >= f["height"]]
        files = [f for f in files if min(f["width"], f["height"]) >= 540]
        if not files:
            continue
        files.sort(key=lambda f: abs(min(f["width"], f["height"]) - target))
        try:
            d = requests.get(files[0]["link"], timeout=120)
            d.raise_for_status()
            if len(d.content) < 50000:
                continue
            path = WORK / f"pexels{idx}.mp4"
            path.write_bytes(d.content)
            used_ids.add(v["id"])
            return path, f"Video: Pexels ({v.get('user', {}).get('name', '')}) {v.get('url', '')}"
        except Exception as e:
            log("Pexels yuklash xatosi:", e)
    return None, None


def make_clip(img, audio, dur, out, text="", idx=0):
    seg_len = 3.0 if MODE == "short" else 4.0
    k = max(1, round(dur / seg_len))
    seg_frames = [int(dur * FPS / k)] * k
    seg_frames[-1] += int(dur * FPS) - sum(seg_frames) + 1
    parts = [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:3[bg0];"
             f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease[fg0];"
             f"[bg0][fg0]overlay=(W-w)/2:(H-h)/2,scale={W * 2}:{H * 2},split={k}" +
             "".join(f"[s{j}]" for j in range(k)) + ";"]
    for j in range(k):
        n = seg_frames[j]
        z, x, y = _motions(n)[(idx * 2 + j) % 6]
        parts.append(f"[s{j}]zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={FPS}[m{j}];")
    parts.append("".join(f"[m{j}]" for j in range(k)) + f"concat=n={k}:v=1:a=0[cat];")
    grade = _finish("cat", text, dur, idx)
    parts.append(grade)
    run([
        "ffmpeg", "-y", "-i", str(img), "-i", str(audio),
        "-filter_complex", "".join(parts), "-map", "[v]", "-map", "1:a",
        "-af", "apad", "-t", f"{dur:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        str(out),
    ])


def build_video(data):
    scenes = data["scenes"]
    audios = make_audio(scenes)
    used_urls, used_vids, credits, clips = set(), set(), [], []
    prev_img = None
    mine = local_clips()
    log(f"Qo'lda yuklangan (Flow) kadrlar: {len(mine)} | Pexels: {'yoqilgan' if PEXELS_KEY else 'kalit yoq'}")
    for i, (s, a) in enumerate(zip(scenes, audios)):
        dur = duration(a) + 0.5
        clip = WORK / f"clip{i}.mp4"
        text = s.get("narration", "")
        src = None
        if i < len(mine):
            src, kind = mine[i], "Flow kadri"
        else:
            src, credit = pexels_video(s.get("video_query", ""), i, used_vids)
            kind = "Pexels video"
            if src:
                credits.append(credit)
        if src:
            make_video_clip(src, a, dur, clip, text, i)
        else:
            kind = "rasm"
            img, credit = fetch_image(s.get("image_query", data["topic"]), data["topic"], i, used_urls)
            if img is None:
                img = prev_img or blank_image(WORK / "blank.png")
                log(f"Sahna {i}: rasm topilmadi, oldingisi ishlatildi")
            else:
                prev_img = img
                credits.append(credit)
            make_clip(img, a, dur, clip, text, i)
        clips.append(clip)
        log(f"Sahna {i + 1}/{len(scenes)} tayyor ({dur:.1f}s, {kind})")

    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
    joined = WORK / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    OUT.mkdir(exist_ok=True)
    final = OUT / "video.mp4"
    if MUSIC.exists():
        run([
            "ffmpeg", "-y", "-i", str(joined), "-stream_loop", "-1", "-i", str(MUSIC),
            "-filter_complex", "[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first,volume=2[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
            str(final),
        ])
    else:
        joined.replace(final)
    return final, credits


def upload(video, data, credits):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    title = data["title"][:100]
    if MODE == "short" and "#shorts" not in title.lower() and len(title) <= 91:
        title += " #Shorts"
    desc = data.get("description", "") + "\n\n"
    if MODE == "short":
        desc += "#Shorts #Historia\n\n"
    desc += "Narración generada con voz sintética (IA).\n\nImágenes: Wikimedia Commons / Vídeos: Pexels\n"
    desc += "\n".join(f"- {c}" for c in credits[:30])
    tags, total = [], 0
    for t in data.get("tags", []):
        t = str(t)[:30]
        if total + len(t) > 450:
            break
        tags.append(t)
        total += len(t)

    def attempt(synthetic):
        status = {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False}
        if synthetic:
            status["containsSyntheticMedia"] = True
        body = {
            "snippet": {"title": title, "description": desc[:4900], "tags": tags, "categoryId": "27",
                        "defaultLanguage": "es", "defaultAudioLanguage": "es"},
            "status": status,
        }
        media = MediaFileUpload(str(video), chunksize=-1, resumable=True, mimetype="video/mp4")
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        return resp

    try:
        resp = attempt(True)
    except HttpError as e:
        log("containsSyntheticMedia bilan xato, qayta urinish:", e)
        resp = attempt(False)
    log("YUKLANDI: https://youtu.be/" + resp["id"], "| holat:", PRIVACY)


def main():
    if not GEMINI_KEY:
        sys.exit("GEMINI_API_KEY topilmadi (GitHub Secrets'ga qo'shing)")
    WORK.mkdir(exist_ok=True)
    used = load_used()
    log(f"Rejim: {MODE} | dry_run={DRY_RUN} | privacy={PRIVACY}")
    data = make_script(used)
    log("Mavzu:", data.get("topic"), "|", data["title"])
    video, credits = build_video(data)
    log("Video tayyor:", video, f"({duration(video):.0f}s)")
    if DRY_RUN:
        log("DRY_RUN: YouTube'ga yuklanmadi. Videoni Actions > Artifacts'dan yuklab oling.")
        return
    upload(video, data, credits)
    save_used(used, data.get("topic", data["title"]))


if __name__ == "__main__":
    main()
    
