# Pult: přepis diktátu. Běží v samostatném Python prostředí s modelem, server Pultu ho jen spouští,
# sám zůstává bez závislostí.
#   asr.py --check            → {"ok": true, "engine": ..., "model": ..., "cached": ..., "available": [...]}
#   asr.py --serve            → čte z stdin řádky {"path": "x.wav", "lang": "cs"}, vrací řádky {"segments": [...]}
# Modely (--model): whisper-turbo (výchozí; Mac s Apple Silicon přes mlx-whisper, jinde faster-whisper)
#                   parakeet-v3   (NVIDIA Parakeet TDT 0.6B v3, menší a rychlejší; Mac přes parakeet-mlx)
import json
import os
import sys

WHISPER_MLX = "mlx-community/whisper-large-v3-turbo"
WHISPER_CT2 = "large-v3-turbo"
WHISPER_LARGE_MLX = "mlx-community/whisper-large-v3-mlx"  # přesnější na češtinu (na Janově nahrávce 16 % chyb proti 38 % u turbo)
WHISPER_LARGE_CT2 = "large-v3"
PARAKEET_MLX = "mlx-community/parakeet-tdt-0.6b-v3"


def has(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def available():
    out = []
    if has("mlx_whisper") or has("faster_whisper"):
        out += ["whisper-large", "whisper-turbo"]
    if has("parakeet_mlx"):
        out.append("parakeet-v3")
    return out


def resolve(model):
    """Klíč modelu z nastavení → (motor, repozitář)."""
    m = (model or "").strip()
    if m in ("parakeet", "parakeet-v3") or "parakeet" in m:
        return "parakeet-mlx", (PARAKEET_MLX if "/" not in m else m)
    # výchozí: velký Whisper na Macu s Apple Silicon (rychlý), turbo jinde (na procesoru by velký byl pomalý)
    if has("mlx_whisper"):
        return "mlx-whisper", (m if "/" in m else WHISPER_MLX if m == "whisper-turbo" else WHISPER_LARGE_MLX)
    if has("faster_whisper"):
        return "faster-whisper", (m if "/" in m else WHISPER_LARGE_CT2 if m == "whisper-large" else WHISPER_CT2)
    return None, None


def cached(repo):
    try:
        from huggingface_hub import try_to_load_from_cache
        repo = repo if "/" in repo else "mobiuslabsgmbh/faster-whisper-" + repo
        p = try_to_load_from_cache(repo, "config.json")
        return isinstance(p, str) and os.path.exists(p)
    except Exception:
        return None


def silent_wav():
    import tempfile
    import wave
    p = os.path.join(tempfile.gettempdir(), "pult-ticho.wav")
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 8000)
    return p


def sentences(words, extra):
    """Slova s časy → věty (konec věty = . ? ! …), každá s časem svého prvního slova."""
    out, cur = [], []
    for i, (w, a, b) in enumerate(words):
        cur.append((w, a, b))
        if w.strip().endswith((".", "?", "!", "…")) or i == len(words) - 1:
            text = "".join(x[0] for x in cur).strip()
            if text:
                out.append(dict(extra, start=float(cur[0][1]), end=float(cur[-1][2]), text=text))
            cur = []
    return out


class Vad:
    """Silero VAD: kde v nahrávce opravdu někdo mluví. Whisper si jinak v tichu a šumu vymýšlí věty
    („Titulky vytvořil JohnyX“, „Konec.“), protože se učil na titulcích z internetu."""

    def __init__(self):
        from silero_vad import load_silero_vad
        self.model = load_silero_vad()

    def regions(self, path):
        import wave
        import numpy as np
        import torch
        from silero_vad import get_speech_timestamps
        with wave.open(path) as w:
            sr = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if sr != 16000 or not len(x):
            return None
        ts = get_speech_timestamps(torch.from_numpy(x), self.model, sampling_rate=16000, threshold=0.5, min_speech_duration_ms=250,
                                   min_silence_duration_ms=300, speech_pad_ms=150, return_seconds=True)
        return [(float(t["start"]), float(t["end"])) for t in ts]


def overlap(a, b, regions):
    return sum(max(0.0, min(b, e) - max(a, s)) for s, e in regions)


class Engine:
    def __init__(self, model=None):
        try:
            self.vad = Vad()
        except Exception:  # bez silero-vad (Windows: faster-whisper má vlastní VAD)
            self.vad = None
        self.kind, self.model = resolve(model)
        if not self.kind:
            raise RuntimeError("chybí mlx-whisper, faster-whisper i parakeet-mlx")
        if self.kind == "mlx-whisper":
            import mlx_whisper
            self.mod = mlx_whisper
        elif self.kind == "faster-whisper":
            from faster_whisper import WhisperModel
            self.fw = WhisperModel(self.model, device="auto", compute_type="int8")
        else:
            from parakeet_mlx import from_pretrained
            self.pk = from_pretrained(self.model)

    def warm(self):
        """Stáhne model (poprvé) a načte ho do paměti: přepis půl vteřiny ticha."""
        self.transcribe(silent_wav())

    def transcribe(self, path, lang="cs", prompt=None):
        regions = None
        if self.vad:
            try:
                regions = self.vad.regions(path)
            except Exception:
                regions = None
            if regions is not None and sum(e - s for s, e in regions) < 0.4:
                return []  # nikdo nemluví: nic nepřepisovat
        out = self._transcribe(path, lang, prompt)
        if regions:
            # věty mimo řeč (vymyšlené v tichu mezi větami) zahodit
            out = [x for x in out if overlap(x["start"], x["end"], regions) >= min(0.35, 0.3 * max(0.05, x["end"] - x["start"]))]
        return out

    def _transcribe(self, path, lang="cs", prompt=None):
        out = []
        # prompt = slovník střihu, název dávky a předchozí nadiktovaná věta: Whisper pak píše jména a výrazy správně
        if self.kind == "mlx-whisper":
            r = self.mod.transcribe(path, path_or_hf_repo=self.model, language=lang, condition_on_previous_text=True,
                                    initial_prompt=prompt or None, verbose=None, fp16=True, word_timestamps=True)
            for s in r.get("segments", []):
                extra = {"no_speech_prob": float(s.get("no_speech_prob") or 0), "avg_logprob": float(s.get("avg_logprob") or 0),
                         "compression_ratio": float(s.get("compression_ratio") or 0)}
                w = s.get("words") or []
                # po větách podle časů slov: každá věta má svůj čas (Whisper jinak spojí víc vět a u první hlásí 0,0)
                out += sentences([(x["word"], x["start"], x["end"]) for x in w], extra) if w else \
                    [dict(extra, start=float(s["start"]), end=float(s["end"]), text=s["text"].strip())]
        elif self.kind == "faster-whisper":
            segs, _info = self.fw.transcribe(path, language=lang, condition_on_previous_text=True, vad_filter=True, beam_size=5,
                                             word_timestamps=True, initial_prompt=prompt or None)
            for s in segs:
                extra = {"no_speech_prob": float(s.no_speech_prob or 0), "avg_logprob": float(s.avg_logprob or 0),
                         "compression_ratio": float(s.compression_ratio or 0)}
                w = s.words or []
                out += sentences([(x.word, x.start, x.end) for x in w], extra) if w else \
                    [dict(extra, start=float(s.start), end=float(s.end), text=s.text.strip())]
        else:
            r = self.pk.transcribe(path)  # Parakeet pozná jazyk sám a vrací věty s přesnými časy
            for s in getattr(r, "sentences", None) or []:
                text = (s.text or "").strip()
                if text:
                    out.append({"start": float(s.start), "end": float(s.end), "text": text})
        return out


def main():
    model = None
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1] or None
    if "--check" in sys.argv:
        kind, repo = resolve(model)
        print(json.dumps({"ok": bool(kind) and (kind != "parakeet-mlx" or has("parakeet_mlx")), "engine": kind, "model": repo,
                          "cached": cached(repo) if repo else None, "available": available(), "python": sys.version.split()[0],
                          "vad": has("silero_vad") or kind == "faster-whisper"}))
        return
    if "--download" in sys.argv:
        eng = Engine(model)
        eng.warm()
        print(json.dumps({"ok": True, "engine": eng.kind, "model": eng.model}))
        return
    if "--serve" in sys.argv:
        out = sys.stdout
        sys.stdout = sys.stderr  # cokoli, co knihovny vypíšou, nesmí rozbít odpovědi na stdout

        def reply(obj):
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")
            out.flush()
        try:
            eng = Engine(model)
            eng.warm()
            reply({"ready": True, "engine": eng.kind, "model": eng.model})
        except Exception as e:  # noqa: BLE001
            reply({"ready": False, "error": str(e)})
            return
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                job = json.loads(line)
                reply({"segments": eng.transcribe(job["path"], job.get("lang") or "cs", job.get("prompt"))})
            except Exception as e:  # noqa: BLE001
                reply({"error": str(e)})
        return
    # jednorázově: asr.py [--model …] soubor.wav
    eng = Engine(model)
    print(json.dumps({"engine": eng.kind, "model": eng.model, "segments": eng.transcribe(sys.argv[-1])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
