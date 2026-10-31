#!/usr/bin/env python3
"""Chat WhatsApp dei clienti nel database ordini (dal 2026-10-31).

    python3 data/carica_whatsapp.py            # riscrive whatsapp_clienti, whatsapp_domande, whatsapp_libretti
    python3 data/carica_whatsapp.py --report   # solo conteggi

Sorgente: Mak/mak-chat-extractor/output/backup/mak_chat.db (backup iPhone -> backup_export.py -> extract.py).
Il codice cliente sta in _codice.txt di ogni cartella chat (scritto da backup_export.py).
Le coppie domanda -> risposta le trova qa_whatsapp.coppie_chat, la stessa regola dell'analisi anonimizzata.
I libretti letti (prova 2026-10-31) arrivano da output/backup/libretti/libretti.json, se c'e'.
Testi in chiaro nel database; build.py li mette nella scheda cliente della pagina cifrata (sezione WhatsApp).
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
import carica_db  # noqa: E402

ESTRATTORE = os.path.normpath(os.path.join(QUI, "..", "..", "mak-chat-extractor"))
CHAT_DB = os.path.join(ESTRATTORE, "output", "backup", "mak_chat.db")
LIBRETTI = os.path.join(ESTRATTORE, "output", "backup", "libretti", "libretti.json")
sys.path.insert(0, ESTRATTORE)


def codice_chat(source):
    p = os.path.join(source or "", "_codice.txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read().strip() or None
    return None


def raccogli(chat_db):
    from qa_whatsapp import argomenti, coppie_chat
    src = sqlite3.connect(chat_db)
    clienti, domande, senza_codice = {}, [], 0
    for chat_id, source in src.execute("SELECT id, source FROM chats"):
        cod = codice_chat(source)
        if not cod:
            senza_codice += 1
            continue
        rows = src.execute("SELECT dt, is_owner, kind, text FROM messages WHERE chat_id=? ORDER BY dt, line_no",
                           (chat_id,)).fetchall()
        if not rows:
            continue
        cli = [r for r in rows if r[2] in ("client_msg", "payment_client")]
        ste = [r for r in rows if r[2] in ("owner_msg", "order_confirm", "payment")]
        att = Counter(k for (k,) in src.execute("SELECT att_kind FROM attachments WHERE chat_id=?", (chat_id,)))
        trovate, senza = coppie_chat(rows)
        arg, minuti = Counter(), []
        for inizio, d, r, m in trovate:
            a = argomenti(d + " " + r)
            arg.update(a)
            minuti.append(m)
            domande.append((cod, inizio.isoformat(timespec="minutes"), d, r, round(m, 1),
                            json.dumps(a, ensure_ascii=False)))
        minuti.sort()
        clienti[cod] = (cod, rows[0][0][:10], rows[-1][0][:10], cli[-1][0][:10] if cli else None,
                        len(cli), len(ste), att["client_photo"] + att["client_doc"], att["client_audio"],
                        len(trovate), senza, minuti[len(minuti) // 2] if minuti else None,
                        json.dumps(dict(arg.most_common()), ensure_ascii=False))
    return clienti, domande, senza_codice


def libretti(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        dati = json.load(f)
    return [(x["codice"], x.get("data_ora"), x.get("marca"), x.get("modello"), x.get("anno"),
             x.get("omologazione"), " | ".join(x.get("pneumatici") or []), 1 if x.get("leggibile") else 0,
             x.get("richiesta"), x.get("risposta")) for x in dati]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chat-db", default=CHAT_DB)
    ap.add_argument("--libretti", default=LIBRETTI)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    if not os.path.exists(a.chat_db):
        raise SystemExit(f"database chat non trovato: {a.chat_db}")
    clienti, domande, senza_codice = raccogli(a.chat_db)
    lib = libretti(a.libretti)
    con = carica_db.apri()
    noti = {r[0] for r in con.execute("SELECT codice FROM clienti UNION SELECT codice FROM anagrafica_b2b")}
    fuori = sum(c not in noti for c in clienti)
    print(f"whatsapp: {len(clienti)} clienti, {len(domande)} domande con risposta, {len(lib)} libretti; "
          f"{senza_codice} chat senza codice, {fuori} codici non nel database ordini")
    if a.report:
        return 0
    ora = datetime.now().isoformat(timespec="seconds")
    with con:
        con.execute("DELETE FROM whatsapp_clienti")
        con.execute("DELETE FROM whatsapp_domande")
        con.execute("DELETE FROM whatsapp_libretti")
        con.executemany("INSERT INTO whatsapp_clienti VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        [v + (ora,) for v in clienti.values()])
        con.executemany("INSERT INTO whatsapp_domande VALUES (?,?,?,?,?,?)", domande)
        con.executemany("INSERT INTO whatsapp_libretti VALUES (?,?,?,?,?,?,?,?,?,?)", lib)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
