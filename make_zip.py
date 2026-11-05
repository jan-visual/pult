#!/usr/bin/env python3
"""Zabalí Pult do jednoho zipu pro macOS i Windows: dist/Pult-<verze>.zip."""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "pult"))
import config  # noqa: E402

NAME = "Pult-%s" % config.VERSION
FILES = ["INSTALL.md", "README.md", "install.py"]
DIRS = ["pult", "skill"]
SKIP_DIRS = {"__pycache__", ".DS_Store"}


def main():
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", NAME + ".zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in FILES:
            z.write(os.path.join(HERE, f), "%s/%s" % (NAME, f))
            n += 1
        for d in DIRS:
            for root, dirs, files in os.walk(os.path.join(HERE, d)):
                dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
                for f in sorted(files):
                    if f in SKIP_DIRS or f.endswith((".pyc", ".tmp")):
                        continue
                    p = os.path.join(root, f)
                    z.write(p, "%s/%s" % (NAME, os.path.relpath(p, HERE).replace(os.sep, "/")))
                    n += 1
    print("%s · %d souborů · %.0f kB" % (out, n, os.path.getsize(out) / 1024))


if __name__ == "__main__":
    main()
