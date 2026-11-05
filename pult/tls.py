# Pult: zabezpečená adresa (https) pro iPad a kolegy v síti. Safari i Chrome pustí mikrofon jen na https
# (nebo na localhost), proto si Pult vyrobí vlastní malou certifikační autoritu a certifikát pro tento počítač.
# Autoritu si iPad jednou nainstaluje (Nastavení › Obecné › Informace › Důvěryhodnost certifikátů).
# Potřebuje příkaz openssl (macOS ho má; Windows ho má s Gitem).
import os
import shutil
import socket
import subprocess
import time

import config

NO_WINDOW = 0x08000000 if config.IS_WIN else 0


def tdir():
    return os.path.join(config.config_dir(), "tls")


def files():
    d = tdir()
    return {k: os.path.join(d, k) for k in ("ca.key", "ca.crt", "server.key", "server.crt", "names.txt")}


def openssl():
    p = shutil.which("openssl")
    if p:
        return p
    for c in ("/usr/bin/openssl", r"C:\Program Files\Git\usr\bin\openssl.exe", r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
        if os.path.isfile(c):
            return c
    return None


def run(args, cwd):
    r = subprocess.run([openssl()] + args, cwd=cwd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "openssl selhal").strip()[-300:])


def ensure(names, ips):
    """Certifikát pro tato jména a IP. Autorita vznikne jednou; certifikát počítače se obnoví, když se změní
    adresy nebo se blíží konec platnosti (iPad bere nejvýš 825 dní)."""
    if not openssl():
        raise RuntimeError("chybí příkaz openssl")
    f = files()
    os.makedirs(tdir(), exist_ok=True)
    host = socket.gethostname().split(".")[0] or "pocitac"
    if not (os.path.isfile(f["ca.key"]) and os.path.isfile(f["ca.crt"])):
        with open(os.path.join(tdir(), "ca.cnf"), "w", encoding="utf-8") as fh:
            fh.write("[req]\ndistinguished_name=dn\n[dn]\n[v3_ca]\nbasicConstraints=critical,CA:TRUE\n"
                     "keyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n")
        run(["req", "-x509", "-new", "-nodes", "-newkey", "rsa:2048", "-sha256", "-days", "3650", "-keyout", "ca.key",
             "-out", "ca.crt", "-subj", "/CN=Pult %s" % host, "-config", "ca.cnf", "-extensions", "v3_ca"], tdir())
    want = sorted(set(n.lower() for n in names if n)) + sorted(set(ips))
    old = open(f["names.txt"], encoding="utf-8").read().split() if os.path.isfile(f["names.txt"]) else []
    fresh = os.path.isfile(f["server.crt"]) and time.time() - os.path.getmtime(f["server.crt"]) < 700 * 86400
    if old == want and fresh:
        return f
    alt = ["DNS.%d = %s" % (i + 1, n) for i, n in enumerate(sorted(set(n.lower() for n in names if n)))]
    alt += ["IP.%d = %s" % (i + 1, ip) for i, ip in enumerate(sorted(set(ips)))]
    with open(os.path.join(tdir(), "server.cnf"), "w", encoding="utf-8") as fh:
        fh.write("[req]\ndistinguished_name=dn\n[dn]\n[v3_req]\nbasicConstraints=CA:FALSE\n"
                 "keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n"
                 "subjectAltName=@alt\nauthorityKeyIdentifier=keyid\n[alt]\n" + "\n".join(alt) + "\n")
    run(["req", "-new", "-nodes", "-newkey", "rsa:2048", "-sha256", "-keyout", "server.key", "-out", "server.csr",
         "-subj", "/CN=%s" % (names[0] if names else "localhost"), "-config", "server.cnf"], tdir())
    run(["x509", "-req", "-in", "server.csr", "-CA", "ca.crt", "-CAkey", "ca.key", "-CAcreateserial", "-out", "server.crt",
         "-days", "800", "-sha256", "-extfile", "server.cnf", "-extensions", "v3_req"], tdir())
    with open(f["names.txt"], "w", encoding="utf-8") as fh:
        fh.write(" ".join(want))
    return f
