# Pult: diktování připomínek. Prohlížeč posílá úseky řeči (zvuk + záznam, kde ve videu člověk zrovna byl),
# tady se přepíšou Whisperem (asr.py ve vlastním Python prostředí) a vloží jako komentáře ke snímku,
# kde člověk začal mluvit. Server sám zůstává bez závislostí; model běží v samostatném procesu.
import base64
import http.client
import json
import os
import secrets
import queue
import re
import subprocess
import threading
import time
import uuid

import config
import library

HERE = os.path.dirname(os.path.abspath(__file__))
jobs = queue.Queue()
emit = lambda msg: None  # noqa: E731  (nastaví server: rozešle zprávu všem prohlížečům)
_check = {"t": 0.0, "v": None}
_proc = {"p": None, "used": 0.0, "lock": threading.Lock()}


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a), flush=True)


# věty, které si Whisper vymýšlí v tichu (titulky z filmů na internetu)
JUNK = re.compile(r"(?i)titulky\s+(vytvo|přelo|pro)|johnyx|kvělec|amara\.org|www\.|^\W*$|^(děkuji|díky)( vám)?( za pozornost| za sledování)?\W*$"
                  r"|^\W*((konec|hello|hmm*|hm|ehm*|eh|no|tak|takže|jo|ano|ahoj|ok|okay)\W*)+$")


# ---------- ElevenLabs Scribe (přepis v cloudu, kvalita jako diktování v ChatGPT) ----------
EL_HOST, EL_PATH, EL_MODEL = "api.elevenlabs.io", "/v1/speech-to-text", "scribe_v2"


def key_path():
    return os.path.join(config.config_dir(), "elevenlabs.key")


def el_key():
    """API klíč: proměnná ELEVENLABS_API_KEY, soubor v nastavení Pultu (jen pro uživatele), nebo Klíčenka (pult-elevenlabs)."""
    k = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if k:
        return k
    try:
        with open(key_path(), encoding="utf-8") as f:
            k = f.read().strip()
        if k:
            return k
    except OSError:
        pass
    if config.IS_MAC:
        try:
            r = subprocess.run(["security", "find-generic-password", "-s", "pult-elevenlabs", "-w"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def el_mask(k):
    return (k[:3] + "…" + k[-4:]) if k else None


def save_el_key(key):
    key = (key or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,200}", key):
        raise ValueError("Tohle nevypadá jako API klíč ElevenLabs.")
    el_request(key, silence_wav())  # ověřit: krátké ticho (stojí zlomek vteřiny kreditu)
    os.makedirs(config.config_dir(), exist_ok=True)
    fd = os.open(key_path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key)
    _check["v"] = None
    return el_mask(key)


def delete_el_key():
    try:
        os.remove(key_path())
    except OSError:
        pass
    _check["v"] = None


def silence_wav():
    import io
    import wave
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 16000)
    return b.getvalue()


def el_request(key, wav_bytes, lang="cs"):
    boundary = "pult-%s" % secrets.token_hex(12)
    fields = {"model_id": EL_MODEL, "language_code": lang, "tag_audio_events": "false", "timestamps_granularity": "word",
              "diarize": "false", "no_verbatim": "false"}
    body = b"".join(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode() for k, v in fields.items())
    body += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"diktat.wav\"\r\nContent-Type: audio/wav\r\n\r\n" % boundary).encode()
    body += wav_bytes + ("\r\n--%s--\r\n" % boundary).encode()
    c = http.client.HTTPSConnection(EL_HOST, timeout=120)
    try:
        c.request("POST", EL_PATH, body=body, headers={"xi-api-key": key, "Accept": "application/json",
                                                       "Content-Type": "multipart/form-data; boundary=%s" % boundary})
        r = c.getresponse()
        data = r.read()
    finally:
        c.close()
    if r.status == 401:
        # 401 vrací ElevenLabs i pro nezaplacené předplatné a došlý kredit: to není chyba klíče
        try:
            why = (json.loads(data).get("detail") or {}).get("status") or ""
        except (ValueError, AttributeError):
            why = ""
        if why == "payment_issue":
            raise RuntimeError("ElevenLabs: předplatné má nezaplacenou fakturu. Klíč je v pořádku, dokonči platbu na elevenlabs.io.")
        if why == "quota_exceeded":
            raise RuntimeError("ElevenLabs: došel kredit. Klíč je v pořádku.")
        raise ValueError("ElevenLabs klíč odmítl (neplatný nebo bez práva na Speech to Text).")
    if r.status >= 300:
        try:
            msg = json.loads(data).get("detail")
            msg = msg.get("message") if isinstance(msg, dict) else msg
        except ValueError:
            msg = data[:200]
        raise RuntimeError("ElevenLabs: %s %s" % (r.status, msg))
    return json.loads(data)


TENS = {"dvacet": 20, "třicet": 30, "čtyřicet": 40, "padesát": 50, "šedesát": 60, "sedmdesát": 70, "osmdesát": 80, "devadesát": 90}
TEENS = {"deset": 10, "jedenáct": 11, "dvanáct": 12, "třináct": 13, "čtrnáct": 14, "patnáct": 15, "šestnáct": 16,
         "sedmnáct": 17, "osmnáct": 18, "devatenáct": 19, "sto": 100}
UNITS = {"jedna": 1, "jeden": 1, "jedno": 1, "dva": 2, "dvě": 2, "tři": 3, "čtyři": 4, "pět": 5, "šest": 6, "sedm": 7, "osm": 8, "devět": 9}
FILLER = re.compile(r"(?i)(^|[\s,.])(eh|ehm|hm|hmm|em)(?=[\s,.!?]|$)[,.]?")


def tidy(text):
    """Čísla od deseti číslicemi (jako ChatGPT: „32 vteřin“), bez „eh“. Malá čísla zůstávají slovy („jednu věc“)."""
    text = FILLER.sub(lambda m: m.group(1) if m.group(1).strip() else " ", text)

    def num(m):
        a, b = m.group(1).lower(), (m.group(2) or "").lower()
        if a in TENS:
            return str(TENS[a] + UNITS.get(b, 0)) + ("" if b in UNITS or not b else " " + m.group(2))
        return str(TEENS[a]) + (" " + m.group(2) if b else "")
    words = "|".join(sorted(list(TENS) + list(TEENS), key=len, reverse=True))
    text = re.sub(r"(?i)\b(%s)\b(?:\s+(%s)\b)?" % (words, "|".join(UNITS)), num, text)
    text = re.sub(r"\s{2,}", " ", re.sub(r"\s+([,.!?])", r"\1", text)).strip(" ,")
    return text[:1].upper() + text[1:]


def el_transcribe(wav):
    key = el_key()
    if not key:
        raise RuntimeError("Chybí API klíč ElevenLabs (Nastavení › Diktování).")
    with open(wav, "rb") as f:
        res = el_request(key, f.read())
    # slova → věty (každá s časem svého prvního slova), stejně jako u Whisperu
    out, cur = [], []
    for w in res.get("words") or []:
        t = w.get("type")
        if t == "audio_event":
            continue
        if t == "spacing":
            if cur:
                cur.append((w.get("text") or " ", None, None))
            continue
        cur.append((w.get("text") or "", w.get("start"), w.get("end")))
        if (w.get("text") or "").strip().endswith((".", "?", "!", "…")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    segs = []
    for sent in out:
        times = [(a, b) for _t, a, b in sent if a is not None]
        text = tidy("".join(t for t, _a, _b in sent).strip())
        if text and times:
            segs.append({"start": float(times[0][0]), "end": float(times[-1][1]), "text": text})
    return segs


def asr_python(cfg=None):
    cfg = cfg or config.load()
    p = (cfg.get("asr_python") or "").strip()
    if p and os.path.isfile(p):
        return p
    venv = os.path.join(config.config_dir(), "asr")
    for cand in (os.path.join(venv, "Scripts", "python.exe"), os.path.join(venv, "bin", "python")):
        if os.path.isfile(cand):
            return cand
    return None


def status(force=False):
    """Je diktování připravené? (výsledek se pamatuje 10 minut)"""
    cfg = config.load()
    key = (cfg.get("dictation", True), cfg.get("asr_python"), cfg.get("asr_model"))
    if not force and _check["v"] is not None and _check.get("key") == key and time.time() - _check["t"] < 600:
        return _check["v"]
    py = asr_python(cfg)
    k = el_key()
    v = {"ready": False, "python": py, "engine": None, "model": None, "cached": None, "reason": "",
         "choice": cfg.get("asr_model") or "whisper-large", "available": [], "el_key": el_mask(k)}
    if v["choice"] == "elevenlabs":
        v.update(engine="elevenlabs", model="Scribe v2 (cloud)", ready=bool(k) and cfg.get("dictation", True),
                 reason="" if k else "Chybí API klíč ElevenLabs (Nastavení › Diktování).")
        if py:  # pro výběr modelů v nastavení
            try:
                r = subprocess.run([py, os.path.join(HERE, "asr.py"), "--check"], capture_output=True, text=True, timeout=60,
                                   creationflags=library.NO_WINDOW)
                v["available"] = json.loads((r.stdout or "").strip().splitlines()[-1]).get("available") or []
            except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                pass
        if k:
            v["available"].append("elevenlabs")
        _check.update(t=time.time(), v=v, key=key)
        return v
    if not cfg.get("dictation", True):
        v["reason"] = "Diktování je vypnuté v nastavení."
    elif not py:
        v["reason"] = "Přepis řeči není nainstalovaný. Řekni Claudovi „zapni v Pultu diktování“."
    else:
        try:
            r = subprocess.run([py, os.path.join(HERE, "asr.py"), "--check", "--model", cfg.get("asr_model") or ""],
                               capture_output=True, text=True, timeout=60, creationflags=library.NO_WINDOW)
            j = json.loads((r.stdout or "").strip().splitlines()[-1])
            v.update(engine=j.get("engine"), model=j.get("model"), cached=j.get("cached"), ready=bool(j.get("ok")),
                     available=j.get("available") or [], vad=bool(j.get("vad")))
            if not v["ready"]:
                v["reason"] = "V prostředí pro přepis chybí zvolený model (%s)." % v["choice"]
        except (OSError, ValueError, IndexError, subprocess.SubprocessError) as e:
            v["reason"] = "Přepis řeči nejde spustit: %s" % e
    if k:
        v["available"].append("elevenlabs")
    if _check.get("key") not in (None, key):
        stop_worker()  # jiné prostředí nebo model: příště se spustí nový proces
    _check.update(t=time.time(), v=v, key=key)
    return v


def cloud():
    return (config.load().get("asr_model") or "") == "elevenlabs"


# ---------- proces s modelem (drží se načtený, po 10 min nečinnosti se ukončí) ----------
def _worker():
    p = _proc["p"]
    if p and p.poll() is None:
        return p
    py = asr_python()
    if not py:
        raise RuntimeError(status()["reason"] or "přepis není nainstalovaný")
    cfg = config.load()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    ff = config.tool("ffmpeg")
    if ff:  # modely si zvuk načítají přes ffmpeg
        env["PATH"] = os.path.dirname(ff) + os.pathsep + env.get("PATH", "")
    p = subprocess.Popen([py, os.path.join(HERE, "asr.py"), "--serve", "--model", cfg.get("asr_model") or ""],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                         encoding="utf-8", bufsize=1, env=env, creationflags=library.NO_WINDOW)
    hello = json.loads(p.stdout.readline() or "{}")  # první řádek až po načtení modelu (poprvé se i stahuje)
    if not hello.get("ready"):
        p.kill()
        raise RuntimeError(hello.get("error") or "model se nenačetl")
    _proc["p"] = p
    return p


# slovník pro přepis: výrazy z revizí videa, ať je Whisper píše správně
VOCAB = ("Připomínky ke střihu videa. Mrkni do toho DaVinci, Premiere, přestříhal, začistil, úderný, záběr, střih, "
         "titulky, Reels, TikTok, Shorts, intro, V4ka, zesílit hudbu, ztlumit, zkrátit pauzu.")


def prompt_for(bid, meta, items):
    """Slovník + název dávky a položky (jména) + předchozí nadiktovaná věta stejného člověka (navázání)."""
    b, _nt = library.get_batch(bid)
    names = {it["n"]: it.get("name") or "" for it in b.get("items", [])}
    ns = sorted({e["n"] for e in meta["log"]})
    parts = [VOCAB, "Dávka: %s." % (b.get("title") or "")] + ["Video: %s." % os.path.splitext(names.get(n, ""))[0].replace("_", " ") for n in ns[:2]]
    prev = ""
    d = ddir(bid)
    try:
        done = [library.load_json(os.path.join(d, f), {}) for f in os.listdir(d) if f.endswith(".json")]
        done = [m for m in done if m.get("state") == "done" and m.get("text") and m.get("from") == meta.get("from") and m.get("at", "") < meta.get("at", "")]
        if done:
            prev = max(done, key=lambda m: m["at"])["text"][-200:]
    except OSError:
        pass
    return " ".join(p for p in parts + [prev] if p.strip())[-600:]


def transcribe(wav, prompt=None):
    with _proc["lock"]:
        for attempt in (1, 2):
            p = _worker()
            try:
                p.stdin.write(json.dumps({"path": wav, "prompt": prompt}) + "\n")
                p.stdin.flush()
                r = json.loads(p.stdout.readline() or "{}")
            except (OSError, ValueError):
                r = {}
            if "segments" in r:
                _proc["used"] = time.time()
                return r["segments"]
            if r.get("error") and attempt == 2:
                raise RuntimeError(r["error"])
            stop_worker()  # spadl nebo neodpověděl: jednou zkusit znovu s novým procesem
        raise RuntimeError("přepis neodpověděl")


def warm():
    """Načíst model dopředu, ať je první přepis hned (volá se při zapnutí mikrofonu)."""
    if cloud():
        return

    def go():
        try:
            with _proc["lock"]:
                _worker()
                _proc["used"] = time.time()
        except Exception as e:  # noqa: BLE001
            log("Diktování: model se nenačetl:", e)
    threading.Thread(target=go, daemon=True).start()


def stop_worker():
    p = _proc["p"]
    _proc["p"] = None
    if p and p.poll() is None:
        try:
            p.stdin.close()
            p.wait(3)
        except (OSError, subprocess.TimeoutExpired):
            p.kill()


def _reaper():
    while True:
        time.sleep(30)
        if _proc["p"] and time.time() - _proc["used"] > 600 and jobs.empty() and _proc["lock"].acquire(blocking=False):
            try:
                stop_worker()
            finally:
                _proc["lock"].release()


# ---------- úseky diktátu ----------
def ddir(bid):
    return os.path.join(library.batch_dir(bid), "diktat")


def save_segment(bid, body):
    """Uloží úsek z prohlížeče (zvuk v base64 + záznam polohy ve videu) a zařadí ho k přepisu."""
    sid = str(body.get("id") or "")
    if not library.safe_id(sid):
        sid = uuid.uuid4().hex[:12]
    audio = str(body.get("audio") or "")
    if not audio.startswith("data:") or "," not in audio:
        raise ValueError("chybí zvuk")
    head, data = audio.split(",", 1)
    ext = "webm" if "webm" in head else "ogg" if "ogg" in head else "m4a" if ("mp4" in head or "aac" in head) else "wav" if "wav" in head else "bin"
    log = [{"t": float(e.get("t") or 0), "n": int(e.get("n") or 0), "v": float(e.get("v") or 0),
            "p": bool(e.get("p")), "r": float(e.get("r") or 1)} for e in (body.get("log") or [])[:20000] if isinstance(e, dict)]
    if not log:
        raise ValueError("chybí záznam polohy ve videu")
    d = ddir(bid)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "%s.%s" % (sid, ext)), "wb") as f:
        f.write(base64.b64decode(data))
    onsets = sorted(float(x) for x in (body.get("onsets") or [])[:2000] if isinstance(x, (int, float)))
    meta = {"id": sid, "batch": bid, "audio": "%s.%s" % (sid, ext), "log": log, "onsets": onsets, "by": str(body.get("by") or "")[:60],
            "byc": str(body.get("byc") or "")[:16], "from": str(body.get("from") or "")[:40], "at": library.now_iso(), "state": "queued"}
    library.save_json(os.path.join(d, sid + ".json"), meta)
    jobs.put((bid, sid))
    return sid


def requeue():
    """Po restartu serveru dopřepsat, co se nestihlo."""
    try:
        for name in os.listdir(library.davky()):
            d = os.path.join(library.davky(), name, "diktat")
            if os.path.isdir(d):
                for f in sorted(os.listdir(d)):
                    if f.endswith(".json"):
                        m = library.load_json(os.path.join(d, f), {})
                        if m.get("state") == "queued":
                            jobs.put((name, m.get("id")))
    except OSError:
        pass


def video_at(log, ms):
    """Kde ve videu člověk byl `ms` milisekund od začátku úseku: (položka, čas v s)."""
    e = log[0]
    for x in log:
        if x["t"] <= ms:
            e = x
        else:
            break
    if e["p"]:
        return e["n"], e["v"] + (ms - e["t"]) / 1000.0 * (e["r"] or 1)
    return e["n"], e["v"]


def to_comments(meta, segments, items):
    """Věty z Whisperu → komentáře. Když člověk mluví u zastaveného videa, věty se spojí do jednoho komentáře."""
    groups = []
    onsets = meta.get("onsets") or []  # kdy mikrofon slyšel začátek řeči (ms od začátku úseku)
    for s in segments:
        text = (s.get("text") or "").strip()
        if not text or JUNK.search(text) or s.get("compression_ratio", 0) > 2.6 or (s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -0.8):
            continue
        start = s["start"] * 1000
        near = [o for o in onsets if abs(o - start) < 700]
        if near:  # přesnější začátek věty podle mikrofonu
            start = min(near, key=lambda o: abs(o - start))
        elif onsets and start < onsets[0]:
            start = onsets[0]
        n, v = video_at(meta["log"], start)
        g = groups[-1] if groups else None
        # spojit jen věty u stojícího videa na stejném místě; při přehrávání má každá věta vlastní čas
        if g and g["n"] == n and s["start"] - g["end"] < 1.6 and abs(v - g["v"]) < 0.3:
            g["text"] += " " + text
            g["end"] = s["end"]
        else:
            groups.append({"n": n, "v": v, "start": s["start"], "end": s["end"], "text": text})
    out = []
    for g in groups:
        it = items.get(g["n"])
        if not it:
            continue
        if it.get("kind") == "video":
            fps = float(it.get("fps") or 30)
            frames = int(it.get("frames") or max(1, int((it.get("duration") or 0) * fps)))
            frame = max(0, min(frames - 1, int(g["v"] * fps + 1e-4)))
        else:
            frame = 0
        out.append({"id": "d%s" % uuid.uuid4().hex[:10], "n": g["n"], "frame": frame, "text": g["text"],
                    "by": meta.get("by") or "", "byc": meta.get("byc") or "", "src": "dict"})
    return out


def process(bid, sid):
    d = ddir(bid)
    mp = os.path.join(d, sid + ".json")
    meta = library.load_json(mp, None)
    if not meta or meta.get("state") != "queued":
        return
    wav = os.path.join(d, sid + ".16k.wav")  # převod vedle originálu (ten může být taky .wav)
    try:
        ff = config.tool("ffmpeg")
        if not ff:
            raise RuntimeError("chybí ffmpeg")
        r = library.run([ff, "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", os.path.join(d, meta["audio"]),
                         "-ac", "1", "-ar", "16000", "-f", "wav", wav], timeout=120)
        if r.returncode != 0:
            raise RuntimeError("zvuk nejde převést: %s" % (r.stderr or "").strip()[-200:])
        t0 = time.time()
        b, _nt = library.get_batch(bid)
        items = {it["n"]: it for it in b.get("items", [])}
        segs = el_transcribe(wav) if cloud() else transcribe(wav, prompt_for(bid, meta, items))
        added = []
        for c in to_comments(meta, segs, items):
            change = library.apply_op(bid, {"op": "comment.set", "comment": c})
            added.append(change["comment"]["id"])
            emit({"type": "notes", "batch": bid, "from": "dictation", "change": change})
        meta.update(state="done", comments=added, text=" ".join(s.get("text", "") for s in segs).strip(), took=round(time.time() - t0, 2))
        emit({"type": "dictation", "batch": bid, "id": sid, "from": meta.get("from"), "state": "done", "count": len(added)})
    except Exception as e:  # noqa: BLE001
        meta.update(state="error", error=str(e))
        log("Diktování: přepis selhal:", e)
        emit({"type": "dictation", "batch": bid, "id": sid, "from": meta.get("from"), "state": "error", "error": str(e)})
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass
        library.save_json(mp, meta)


def _loop():
    while True:
        bid, sid = jobs.get()
        try:
            process(bid, sid)
        except Exception as e:  # noqa: BLE001
            log("Diktování:", e)


def start(emit_fn):
    global emit
    emit = emit_fn
    threading.Thread(target=_loop, daemon=True).start()
    threading.Thread(target=_reaper, daemon=True).start()
    requeue()
