#!/usr/bin/env python3
"""Rigenera e pubblica la pagina ordini (con le telefonate) solo se i dati sono cambiati.

Lo lancia ogni sera Mak/Plaud Note Pro/notturno.sh, dopo l'import delle telefonate.
- passphrase dal Portachiavi (voce «mak-ordini-pass», come il briefing) o da MAK_ORDINI_PASS;
- se ordini e telefonate sono identici all'ultima pubblicazione, non fa nulla;
- se l'ultimo commit è solo una build automatica della pagina, lo sostituisce
  (amend + push --force-with-lease): GitHub non accumula una copia da 2 MB a sera.
  Altrimenti fa un commit normale.

Uso:
    python3 data/pubblica.py                 # build + pubblicazione se serve
    python3 data/pubblica.py --non-pubblicare
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
sys.path.insert(0, QUI)
import build  # noqa: E402

PORTACHIAVI = "mak-ordini-pass"
FIRMA = os.path.join(QUI, "log", "pubblicato.sha256")
PREFISSO = "Pagina ordini: build"


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=RADICE, capture_output=True, text=True,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def impronta() -> str:
    """Impronta dei dati pubblicati, senza la data del build (che cambia sempre)."""
    with open(build.PLAIN, encoding="utf-8") as f:
        d = json.load(f)
    d["meta"].pop("build", None)
    return hashlib.sha256(json.dumps(d, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--non-pubblicare", action="store_true")
    a = ap.parse_args()

    p = os.environ.get("MAK_ORDINI_PASS") or subprocess.run(
        ["security", "find-generic-password", "-s", PORTACHIAVI, "-w"], capture_output=True, text=True).stdout.strip()
    if not p:
        sys.exit(f"passphrase assente dal Portachiavi (voce {PORTACHIAVI})")
    build.build(passphrase=p)
    nuova = impronta()
    vecchia = open(FIRMA).read().strip() if os.path.exists(FIRMA) else ""
    if nuova == vecchia:
        # la pagina appena ricostruita è uguale nei dati a quella online: si rimette quella di git
        git("checkout", "--", "index.html", check=False)
        print("pagina: nessun dato nuovo, niente da pubblicare")
        return
    if a.non_pubblicare:
        print("pagina ricostruita, non pubblicata (--non-pubblicare)")
        return

    oggi = datetime.date.today().isoformat()
    git("add", "index.html")
    ultimo = git("log", "-1", "--format=%s")
    file_ultimo = git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").split()
    if ultimo.startswith(PREFISSO) and file_ultimo == ["index.html"]:
        git("commit", "--amend", "-m", f"{PREFISSO} {oggi}")
        git("push", "--force-with-lease")
        modo = "sostituita"
    else:
        git("commit", "-m", f"{PREFISSO} {oggi}")
        git("push")
        modo = "nuovo commit"
    os.makedirs(os.path.dirname(FIRMA), exist_ok=True)
    with open(FIRMA, "w") as f:
        f.write(nuova)
    print(f"pagina pubblicata ({modo})")


if __name__ == "__main__":
    main()
