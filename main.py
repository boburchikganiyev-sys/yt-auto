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
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

VOICE = os.environ.get("TTS_VOICE", "es-MX-JorgeNeural")
RATE = "+8%" if MODE == "short" else "+0%"

W, H = (1080, 1920) if MODE == "short" else (1920, 1080)
FPS = 25

ROOT = Path(__file__).parent
WORK = ROOT / "work"
OUT = ROOT / "output"
USED_FILE = ROOT / "used_topics.json"
MUSIC = ROOT / "music.mp3"

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
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0},
    }
    last = None
    for attempt in range(4):
        try:
            r = requests.post(url, params={"key": GEMINI_KEY}, json=body, timeout=180)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except Exception as e:
            last = e
            log(f"Gemini urinish {attempt + 1} muvaffaqiyatsiz: {e}")
            time.sleep(8 * (attempt + 1))
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

Faqat quyidagi JSON'ni qaytar:
{{
 "topic": "qisqa mavzu nomi (ispancha)",
 "title": "YouTube sarlavhasi, ispancha, qiziqarli, 70 belgigacha",
 "description": "2-3 gaplik ispancha tavsif",
 "tags": ["8-12 ta ispancha teg"],
 "scenes": [ {{"narration": "...", "image_query": "..."}} ]
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
    out = run(["ffprobe", "-v", "error", "-show_entries", "forma
