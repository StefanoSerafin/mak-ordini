#!/usr/bin/env python3
"""Da data/ordini.db a index.html (dataset cifrato inline).

    MAK_ORDINI_PASS='passphrase lunga' python3 data/build.py
    python3 data/build.py            # chiede la passphrase a terminale

Cosa fa:
  1. legge il DB e costruisce un dataset MINIMIZZATO (niente P.IVA, codice
     fiscale, via, CAP, termini di pagamento);
  2. lo salva in chiaro in data/ordini.plain.json (ignorato da git, per debug);
  3. lo cifra: chiave = PBKDF2-SHA256(passphrase, salt, 600k) -> AES-GCM-256;
  4. lo inserisce in index.template.html e scrive index.html.

La passphrase non e' nel repo. Minimo 16 caratteri: il file e' pubblico e un
PIN corto si forza offline in pochi minuti.

Dipendenze: pip3 install cryptography
"""
import base64
import datetime
import getpass
import hashlib
import json
import os
import sqlite3
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
DB = os.path.join(QUI, "ordini.db")
TEMPLATE = os.path.join(RADICE, "index.template.html")
USCITA = os.path.join(RADICE, "index.html")
PLAIN = os.path.join(QUI, "ordini.plain.json")

PBKDF2_ITER = 600_000
MIN_PASS = 16
UTENTE = {"agente": "a", "cliente": "c"}
# La pagina mostra gli ordini da questa data. Il DB locale contiene anche il 2025
# (per i confronti anno su anno): entrera' in pagina quando ci saranno le viste di confronto.
PAGINA_DAL = "2026-01-01"


def dataset(dal=PAGINA_DAL):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cat = [r["categoria"] for r in con.execute(
        "SELECT r.categoria, SUM(r.importo) s FROM righe r JOIN ordini o ON o.id=r.ordine_id"
        " WHERE o.data_ora >= ? GROUP BY r.categoria ORDER BY s DESC", (dal,))]
    icat = {c: i for i, c in enumerate(cat)}
    clienti, icli = [], {}
    for r in con.execute("SELECT codice, ragione_sociale, citta, provincia, flag_cliente, in_anagrafica,"
                         " network, tipo"
                         " FROM clienti WHERE codice IN (SELECT codice_cliente FROM ordini WHERE data_ora >= ?)"
                         " ORDER BY ragione_sociale", (dal,)):
        icli[r["codice"]] = len(clienti)
        clienti.append([r["codice"], r["ragione_sociale"], r["citta"] or "", r["provincia"] or "",
                        r["flag_cliente"] or "", r["in_anagrafica"] or 0,
                        r["network"] or "", r["tipo"] or ""])
    righe = {}
    # omaggi: restano visibili (articoli e pezzi) ma valgono 0, per non gonfiare i totali
    omaggi = {r["id"] for r in con.execute("SELECT id FROM ordini WHERE omaggio=1")}
    for r in con.execute("SELECT ordine_id, cod_articolo, descrizione, applicazione, qta, prezzo, sconto,"
                         " importo, categoria, coupon FROM righe WHERE ordine_id IN"
                         " (SELECT id FROM ordini WHERE data_ora >= ?) ORDER BY ordine_id, n_riga", (dal,)):
        om = r["ordine_id"] in omaggi
        righe.setdefault(r["ordine_id"], []).append([
            r["cod_articolo"], r["descrizione"], r["applicazione"] or "", r["qta"], 0 if om else r["prezzo"],
            r["sconto"] or "", 0 if om else r["importo"], icat[r["categoria"]], r["coupon"] or ""])
    ordini = []
    for r in con.execute("SELECT id, codice_cliente, data_ora, inserito_da, kit_completo, merce_righe,"
                         " spedizione, imponibile FROM ordini WHERE data_ora >= ? ORDER BY data_ora DESC", (dal,)):
        om = r["id"] in omaggi
        ordini.append([r["id"], icli[r["codice_cliente"]], (r["data_ora"] or "")[:16],
                       UTENTE.get(r["inserito_da"], "x"), r["kit_completo"] or 0, 0 if om else r["merce_righe"],
                       r["spedizione"] or 0, 0 if om else (r["imponibile"] or 0), righe.get(r["id"], []),
                       1 if om else 0])
    per = con.execute("SELECT MIN(data_ora) a, MAX(data_ora) b FROM ordini WHERE data_ora >= ?", (dal,)).fetchone()
    meta = {
        "build": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "dal": (per["a"] or "")[:10], "al": (per["b"] or "")[:10],
        "ordini": len(ordini), "clienti": len(clienti),
    }
    # formato posizionale (array) per tenere piccolo il file: le chiavi sono in index.template.html
    return {"meta": meta, "cat": cat, "clienti": clienti, "ordini": ordini}


def cifra(plaintext, passphrase):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        sys.exit("Manca cryptography: pip3 install cryptography")
    salt, iv = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, PBKDF2_ITER, dklen=32)
    ct = AESGCM(key).encrypt(iv, plaintext, None)
    b = lambda x: base64.b64encode(x).decode("ascii")
    return b(salt) + "." + b(iv) + "." + b(ct)


def build(passphrase=None, verbose=True):
    if not os.path.exists(DB):
        sys.exit("Manca data/ordini.db: lancia prima carica_db.py")
    passphrase = passphrase or os.environ.get("MAK_ORDINI_PASS") or getpass.getpass("Passphrase ordini: ")
    if len(passphrase) < MIN_PASS:
        sys.exit(f"Passphrase troppo corta: servono almeno {MIN_PASS} caratteri (es. 4-5 parole a caso).")
    d = dataset()
    plain = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    with open(PLAIN, "w", encoding="utf-8") as f:
        f.write(plain)
    payload = cifra(plain.encode("utf-8"), passphrase)
    # in chiaro nella pagina vanno solo dati non sensibili: parametri di cifratura e data del build
    meta_pubblica = {"kdf": "PBKDF2-SHA256", "iter": PBKDF2_ITER, "cipher": "AES-GCM", "build": d["meta"]["build"]}
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    for segnaposto in ("__PAYLOAD__", "__BUILD_META__"):
        if html.count(segnaposto) != 1:
            sys.exit(f"Il template deve contenere una sola volta {segnaposto}")
    html = html.replace("__PAYLOAD__", payload).replace("__BUILD_META__", json.dumps(meta_pubblica))
    with open(USCITA, "w", encoding="utf-8") as f:
        f.write(html)
    if verbose:
        print(f"index.html: {os.path.getsize(USCITA) / 1024:.0f} KB | {d['meta']['ordini']} ordini, "
              f"{d['meta']['clienti']} clienti, periodo {d['meta']['dal']} -> {d['meta']['al']}")
    return d["meta"]


if __name__ == "__main__":
    build()
