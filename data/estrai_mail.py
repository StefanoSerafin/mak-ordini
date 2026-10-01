#!/usr/bin/env python3
"""Estrae da Mail (account MAK, casella Ordini) i PDF delle notifiche
"Nuovo Ordine" del B2B.

Legge SOLO la casella Ordini e SOLO i messaggi dalla data di cutoff in poi:
scorre la casella a blocchi partendo dal messaggio piu' recente e si ferma al
primo messaggio piu' vecchio del cutoff. Non interroga mai il resto
dell'archivio ne' altre caselle.

Pilota Mail via osascript: Mail deve essere aperta. Incrementale: salta gli
messaggi gia' trattati (data/log/messaggi.json) e smette di scorrere quando un
intero blocco e' gia' noto. Riprendibile: dopo un'interruzione basta rilanciare
con --completo, i blocchi gia' fatti scorrono in pochi secondi.

    python3 data/estrai_mail.py                # dal 2025-01-01
    python3 data/estrai_mail.py --limite 20    # prova
    python3 data/estrai_mail.py --completo     # riscorre tutto il periodo
"""
import argparse
import csv
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

QUI = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(QUI, "pdf")
LOG_DIR = os.path.join(QUI, "log")
STATO = os.path.join(LOG_DIR, "messaggi.json")
PROFILI = os.path.join(LOG_DIR, "profili.json")

ACCOUNT = "MAK"
CASELLA = "Ordini"
DAL_MINIMO = datetime.date(2025, 1, 1)   # non si scende mai sotto questa data (2025 aggiunto su richiesta, 2026-10-01)
BLOCCO = 50
SEP = "\x1f"

RE_ID = re.compile(r"\bI_(\d+)\b")
RE_INOLTRO = re.compile(r"^\s*(R|I|RE|FW|FWD)\s*:", re.I)


def osa(script, timeout):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout + 30)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.rstrip("\n")


def elabora_blocco(inizio, dal, noti, tmp, salva=True):
    """Messaggi inizio..inizio+BLOCCO-1 della casella Ordini (1 = piu' recente).
    In un'unica chiamata: legge id e oggetto e salva in tmp/<msg_id>.pdf
    l'allegato dei "Nuovo Ordine" non ancora noti. Si ferma al primo messaggio
    piu' vecchio del cutoff. Ritorna (lista di dict, finito).
    Per gli stessi messaggi legge anche l'inizio del corpo, dove ci sono
    Network / Tipo / Marca del cliente (nel PDF non compaiono).
    Con salva=False non scarica nulla: serve a completare i profili.

    Nota di velocita': si chiede a Mail la lista dei riferimenti una volta sola
    e poi si interroga ogni riferimento; indirizzare i messaggi per indice o
    leggere le proprieta' "a intervallo" e' 5-10 volte piu' lento."""
    fine = inizio + BLOCCO - 1
    lista_noti = ", ".join(str(n) for n in noti) or "0"
    script = f"""with timeout of 500 seconds
tell application "Mail"
set mb to mailbox "{CASELLA}" of account "{ACCOUNT}"
set cutoff to current date
set day of cutoff to 1
set year of cutoff to {dal.year}
set month of cutoff to {dal.month}
set day of cutoff to {dal.day}
set time of cutoff to 0
set noti to {{{lista_noti}}}
set out to {{}}
try
set ms to messages {inizio} thru {fine} of mb
on error
set ms to messages {inizio} thru -1 of mb
end try
repeat with m in ms
if (date received of m) < cutoff then
set end of out to "FINE"
exit repeat
end if
set mid to id of m
set sogg to subject of m
set esito to "-"
set corpo to ""
if (noti does not contain mid) and (sogg contains "Nuovo Ordine") and (sogg does not start with "R:") and (sogg does not start with "I:") and (sogg does not start with "Re:") and (sogg does not start with "RE:") and (sogg does not start with "Fw") then
try
set c to content of m
if (length of c) > 300 then set c to text 1 thru 300 of c
set AppleScript's text item delimiters to {{return, linefeed, character id 8232, character id 8233}}
set parti to text items of c
set AppleScript's text item delimiters to "|"
set corpo to parti as string
end try
if {"true" if salva else "false"} then
try
set esito to "nessun allegato PDF"
repeat with att in mail attachments of m
if (name of att) ends with ".pdf" or (name of att) ends with ".PDF" then
save att in POSIX file ("{tmp}/" & (mid as string) & ".pdf")
set esito to "ok"
exit repeat
end if
end repeat
on error errm
set esito to "errore: " & errm
end try
end if
end if
set end of out to (mid as string) & "{SEP}" & esito & "{SEP}" & corpo & "{SEP}" & sogg
end repeat
end tell
set AppleScript's text item delimiters to linefeed
return out as string
end timeout"""
    righe, finito = [], False
    for riga in osa(script, 500).splitlines():
        if riga == "FINE":
            finito = True
            break
        p = riga.split(SEP, 3)
        if len(p) == 4:
            righe.append({"msg_id": int(p[0]), "esito": p[1], "profilo": profilo(p[2]), "oggetto": p[3]})
    if len(righe) < BLOCCO:
        finito = True
    return righe, finito


def profilo(corpo):
    """Dall'inizio del corpo ("...|Network|DRIVER|Tipo|Gommisti|Marca||Account|...")
    a {"network", "tipo", "marca"}; None se il corpo non e' stato letto."""
    if "|Network|" not in corpo:
        return None
    campi = corpo.split("|")
    def dopo(etichetta, stop):
        try:
            v = campi[campi.index(etichetta) + 1].strip()
        except (ValueError, IndexError):
            return ""
        return "" if v in stop else v
    return {"network": dopo("Network", ("Tipo",)), "tipo": dopo("Tipo", ("Marca",)),
            "marca": dopo("Marca", ("Account",))}


def _profili():
    try:
        with open(PROFILI, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def completa_profili(dal=DAL_MINIMO, verbose=True):
    """Legge Network/Tipo/Marca per gli ordini gia' scaricati che non li hanno.
    Non scarica allegati."""
    log = print if verbose else (lambda *a, **k: None)
    stato, profili = _stato(), _profili()
    fatti = {mid for mid, v in stato.items() if v.startswith("scarto:") or v in profili}
    mancanti = len(stato) - len(fatti)
    inizio, letti = 1, 0
    while mancanti > 0:
        righe, finito = elabora_blocco(inizio, dal, sorted(fatti), "/dev/null", salva=False)
        for m in righe:
            oid = stato.get(m["msg_id"])
            if oid and not oid.startswith("scarto:") and m["profilo"] is not None:
                profili[oid] = m["profilo"]
                fatti.add(m["msg_id"])
                letti += 1
        with open(PROFILI, "w", encoding="utf-8") as f:
            json.dump(profili, f, ensure_ascii=False)
        log(f"  profili: messaggi {inizio}-{inizio + len(righe) - 1}, letti finora {letti}", flush=True)
        if finito:
            break
        inizio += BLOCCO
    log(f"Profili cliente letti: {letti} | ordini con profilo: {len(profili)}")
    return {"letti": letti, "totale": len(profili)}


def classifica(oggetto):
    """-> (ordine_id | None, motivo_scarto | None)"""
    if RE_INOLTRO.match(oggetto):
        return None, "inoltro/risposta"
    if "Nuovo Ordine" not in oggetto:
        return None, "non e' un Nuovo Ordine"
    mm = RE_ID.search(oggetto)
    if not mm:
        return None, "ID ordine assente nell'oggetto"
    return "I_" + mm.group(1), None


def _log_csv(nome, righe, intestazione):
    with open(os.path.join(LOG_DIR, nome), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(intestazione)
        w.writerows(righe)


def _stato():
    try:
        with open(STATO, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def estrai(dal=DAL_MINIMO, limite=None, completo=False, verbose=True, da_indice=1):
    if dal < DAL_MINIMO:
        raise SystemExit(f"Il cutoff non puo' essere precedente al {DAL_MINIMO.isoformat()}.")
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    log = print if verbose else (lambda *a, **k: None)

    # stato: msg_id di Mail -> ordine (o motivo di scarto) per i messaggi gia' trattati
    stato = _stato()
    profili = _profili()
    presenti = {f[:-4] for f in os.listdir(PDF_DIR) if f.endswith(".pdf")}
    # un PDF cancellato a mano va riscaricato: il suo messaggio torna "non noto"
    stato = {k: v for k, v in stato.items() if v.startswith("scarto:") or v in presenti}

    assegnati = {v for v in stato.values() if not v.startswith("scarto:")}
    letti = salvati = 0
    errori = []
    inizio = max(1, da_indice)
    tmp = None
    try:
        while True:
            # cartella temporanea nuova a ogni blocco: su giri lunghi Mail a un certo
            # punto perde il permesso di scrivere in quella vecchia
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
            tmp = tempfile.mkdtemp(prefix="makordini_")
            righe, finito = None, False
            for _ in (1, 2):
                try:
                    righe, finito = elabora_blocco(inizio, dal, sorted(stato), tmp)
                    break
                except Exception as e:
                    err = str(e)
            if righe is None:
                raise SystemExit(f"Mail non risponde sul blocco {inizio}: {err}\n"
                                 "I PDF gia' salvati restano: rilancia per riprendere.")
            letti += len(righe)
            nuovi = 0
            for m in righe:
                mid = m["msg_id"]
                if mid in stato:
                    continue
                nuovi += 1
                oid, motivo = classifica(m["oggetto"])
                if motivo:
                    stato[mid] = "scarto:" + motivo
                    continue
                if m["profilo"] is not None:
                    profili[oid] = m["profilo"]
                src = os.path.join(tmp, f"{mid}.pdf")
                if m["esito"] != "ok" or not os.path.exists(src) or os.path.getsize(src) == 0:
                    errori.append([oid, m["esito"] if m["esito"] != "ok" else "allegato non salvato"])
                    if os.path.exists(src):
                        os.remove(src)
                    continue
                if oid in presenti:
                    os.remove(src)
                    if oid in assegnati:
                        stato[mid] = "scarto:doppione dello stesso ordine"
                    else:               # PDF gia' su disco ma senza stato: lo si adotta
                        stato[mid] = oid
                        assegnati.add(oid)
                    continue
                shutil.move(src, os.path.join(PDF_DIR, oid + ".pdf"))
                presenti.add(oid)
                stato[mid] = oid
                assegnati.add(oid)
                salvati += 1
            with open(STATO, "w", encoding="utf-8") as f:
                json.dump(stato, f)
            with open(PROFILI, "w", encoding="utf-8") as f:
                json.dump(profili, f, ensure_ascii=False)
            log(f"  messaggi {inizio}-{inizio + len(righe) - 1}: nuovi {nuovi}, "
                f"PDF salvati finora {salvati}, errori {len(errori)}", flush=True)
            if finito:
                break
            if not completo and nuovi == 0:
                break   # aggiornamento: un blocco intero gia' noto -> il resto lo e' gia'
            if limite and salvati >= limite:
                break
            inizio += BLOCCO
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    scarti = [[k, v[len("scarto:"):]] for k, v in sorted(stato.items()) if v.startswith("scarto:")]
    _log_csv("scarti.csv", scarti, ["msg_id", "motivo"])
    _log_csv("errori.csv", errori, ["ordine", "errore"])
    log(f"Casella {CASELLA} dal {dal.isoformat()}: letti {letti} messaggi, salvati {salvati} PDF, "
        f"{len(errori)} errori, {len(scarti)} scartati in totale")
    return {"letti": letti, "salvati": salvati, "errori": len(errori), "scarti": len(scarti),
            "pdf_totali": len(presenti)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dal", default=DAL_MINIMO.isoformat(), help="data minima (YYYY-MM-DD), non prima del 2025-01-01")
    ap.add_argument("--limite", type=int, help="scarica al massimo N ordini (prova)")
    ap.add_argument("--completo", action="store_true", help="riscorre tutto il periodo anche se i primi blocchi sono gia' noti")
    ap.add_argument("--da-indice", type=int, default=1, help="parte dal messaggio N della casella (1 = piu' recente): per riprendere un caricamento lungo senza riscorrere i blocchi gia' fatti")
    ap.add_argument("--profili", action="store_true", help="completa Network/Tipo/Marca degli ordini gia' scaricati, senza scaricare nulla")
    a = ap.parse_args()
    if a.profili:
        print(completa_profili(datetime.date.fromisoformat(a.dal)))
        return 0
    print(estrai(datetime.date.fromisoformat(a.dal), a.limite, a.completo, da_indice=a.da_indice))
    return 0


if __name__ == "__main__":
    sys.exit(main())
