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
import re
import sqlite3
import sys

import coordinate

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
DB = os.path.join(QUI, "ordini.db")
TEMPLATE = os.path.join(RADICE, "index.template.html")
USCITA = os.path.join(RADICE, "index.html")
PLAIN = os.path.join(QUI, "ordini.plain.json")

PBKDF2_ITER = 600_000
MIN_PASS = 16
UTENTE = {"agente": "a", "cliente": "c"}
# La pagina contiene gli ordini da questa data: anno corrente + anno precedente,
# per le viste di confronto (sezione Confronto e scheda cliente).
PAGINA_DAL = "2025-01-01"

# Mappa sensori: marca dalla descrizione delle righe della categoria TPMS / MATE.
# MX Universal = Autel (MX-Sensor); SI2024/SI2048/SI2076 = Huf (conferma di Stefano,
# 2026-10-18). I kit valvole di ricambio non dicono quale sensore monta il cliente.
# Stessa regola, per il popup, in index.template.html (SENS_ESCLUSI).
CAT_SENSORI = "TPMS / MATE"
RE_ESCLUSI = re.compile(r"^REPLAC\.KIT")
RE_AUTEL = re.compile(r"AUTEL|MX UNIVERS")
RE_MATE = re.compile(r"MULTIS|MULT\.TPMS|HUF|TPMS SI\d")
FERMO_GIORNI = 180  # oltre: pallino sbiadito
VENDOR = os.path.join(QUI, "vendor")


def dataset(dal=PAGINA_DAL):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cat = [r["categoria"] for r in con.execute(
        "SELECT r.categoria, SUM(r.importo) s FROM righe r JOIN ordini o ON o.id=r.ordine_id"
        " WHERE o.data_ora >= ? AND COALESCE(o.annullato,0)=0 GROUP BY r.categoria ORDER BY s DESC", (dal,))]
    icat = {c: i for i, c in enumerate(cat)}
    anag = anagrafica(con)
    clienti, icli = [], {}
    for r in con.execute("SELECT codice, ragione_sociale, citta, provincia, flag_cliente, in_anagrafica,"
                         " network, tipo"
                         " FROM clienti WHERE codice IN (SELECT codice_cliente FROM ordini WHERE data_ora >= ?)"
                         " ORDER BY ragione_sociale", (dal,)):
        icli[r["codice"]] = len(clienti)
        clienti.append([r["codice"], r["ragione_sociale"], r["citta"] or "", r["provincia"] or "",
                        r["flag_cliente"] or "", r["in_anagrafica"] or 0,
                        r["network"] or "", r["tipo"] or "", anag.get(r["codice"], 0)])
    righe = {}

    def icat_di(c):
        if c not in icat:
            icat[c] = len(cat)
            cat.append(c)
        return icat[c]
    vett, righe_gest = {}, {}
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gestionale_righe'").fetchone():
        for g in con.execute("SELECT ordine_id, cod_articolo, descrizione, qta_ord, imp_ord, categoria,"
                             " auto_marca, auto_modello FROM gestionale_righe WHERE dt_ord >= ?", (dal[:10],)):
            v = " ".join(x for x in (g["auto_marca"], g["auto_modello"]) if x)
            if v:
                vett.setdefault((g["ordine_id"], g["cod_articolo"]), v)
            q = g["qta_ord"] or 0
            righe_gest.setdefault(g["ordine_id"], []).append([
                g["cod_articolo"], g["descrizione"], v, q, round((g["imp_ord"] or 0) / q, 2) if q else 0, "",
                g["imp_ord"] or 0, icat_di(g["categoria"]), ""])
    # omaggi: restano visibili (articoli e pezzi) ma valgono 0, per non gonfiare i totali
    omaggi = {r["id"] for r in con.execute("SELECT id FROM ordini WHERE omaggio=1")}
    for r in con.execute("SELECT ordine_id, cod_articolo, descrizione, applicazione, qta, prezzo, sconto,"
                         " importo, categoria, coupon FROM righe WHERE ordine_id IN"
                         " (SELECT id FROM ordini WHERE data_ora >= ?) ORDER BY ordine_id, n_riga", (dal,)):
        om = r["ordine_id"] in omaggi
        righe.setdefault(r["ordine_id"], []).append([
            r["cod_articolo"], r["descrizione"], r["applicazione"] or vett.get((r["ordine_id"], r["cod_articolo"]), ""),
            r["qta"], 0 if om else r["prezzo"],
            r["sconto"] or "", 0 if om else r["importo"], icat_di(r["categoria"]), r["coupon"] or ""])
    ordini, annullati = [], []
    for r in con.execute("SELECT id, codice_cliente, data_ora, inserito_da, kit_completo, merce_righe,"
                         " spedizione, imponibile, merce_gestionale, fonte, annullato FROM ordini"
                         " WHERE data_ora >= ? ORDER BY data_ora DESC", (dal,)):
        om = r["id"] in omaggi
        if r["annullato"]:
            # notificato per email ma assente dal gestionale: in pagina solo nella scheda cliente, a 0
            annullati.append([r["id"], icli[r["codice_cliente"]], (r["data_ora"] or "")[:16], r["merce_righe"] or 0,
                              righe.get(r["id"], [])])
            continue
        merce = r["merce_righe"] if r["merce_gestionale"] is None else r["merce_gestionale"]
        rr = righe.get(r["id"], [])
        flag = ""
        if r["fonte"] == "gestionale":
            flag = "g"                   # solo nel gestionale: nessuna email (sede, email mancante)
        elif r["merce_gestionale"] is not None and abs(r["merce_gestionale"] - (r["merce_righe"] or 0)) > 0.5:
            flag = "m"                   # modificato dopo l'invio: righe e importi del gestionale
            rr = righe_gest.get(r["id"], rr)
        ordini.append([r["id"], icli[r["codice_cliente"]], (r["data_ora"] or "")[:16],
                       UTENTE.get(r["inserito_da"], "x"), r["kit_completo"] or 0, 0 if om else merce,
                       r["spedizione"] or 0, 0 if om else (r["imponibile"] or 0), [x[:6] + [0 if om else x[6]] + x[7:] for x in rr],
                       1 if om else 0, flag])
    tel = telefonate(clienti, icli)
    prev = preventivi(con, clienti, icli)
    per = con.execute("SELECT MIN(data_ora) a, MAX(data_ora) b FROM ordini WHERE data_ora >= ?", (dal,)).fetchone()
    meta = {
        "build": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "dal": (per["a"] or "")[:10], "al": (per["b"] or "")[:10],
        "ordini": len(ordini), "clienti": len(clienti), "telefonate": len(tel), "preventivi": len(prev),
    }
    sens, senza = sensori(con, icli, meta["al"], dal)
    meta["sens"] = {m: sum(1 for s in sens if s[3] == m) for m in "AMX"}
    meta["sens"]["senza_coord"] = senza
    # formato posizionale (array) per tenere piccolo il file: le chiavi sono in index.template.html
    meta["annullati"] = len(annullati)
    ap = aperti(con, icli, dal)
    meta["aperti"] = len(ap)
    meta["gestionale"] = gestionale_al(con)
    return {"meta": meta, "cat": cat, "clienti": clienti, "ordini": ordini, "tel": tel, "sens": sens, "prev": prev,
            "ann": annullati, "aperti": ap}


def anagrafica(con):
    """{codice: [listino, pagamento, ultimo accesso B2B, tool TPMS, WhatsApp, fatturato anno prec., fatturato
    anno corr., priorita', B2B attivo, ultimo acquisto TPMS universali, campagna]} dall'anagrafica del gestionale.
    Solo colonne commerciali: niente credenziali, telefoni, email, indirizzi."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='anagrafica_b2b'").fetchone():
        return {}
    out = {}
    for a in con.execute("SELECT * FROM anagrafica_b2b"):
        tool = " · ".join(x for x in (a["tool_autel"], a["tool_ateq"], a["tool_orange"]) if x) or (a["tool_tpms"] or "")
        out[a["codice"]] = [a["listino"] or "", a["pagamento"] or "", a["b2b_ultimo"] or "", tool, a["whatsapp"] or "",
                            a["fatt_prec"] or 0, a["fatt_corr"] or 0, a["priorita"] or "", a["b2b"] or 0,
                            a["ult_acq_tpms"] or "", a["campagna"] or ""]
    return out


def aperti(con, icli, dal=PAGINA_DAL):
    """Merce ordinata e non ancora spedita, dall'ultimo export del gestionale:
    [indice cliente, id ordine, data ordine, codice, descrizione, qta residua, importo residuo, consegna, vettura]."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gestionale_righe'").fetchone():
        return []
    out = []
    for g in con.execute("SELECT * FROM gestionale_righe WHERE qta_res > 0 AND dt_ord >= ? ORDER BY dt_ord DESC",
                         (dal[:10],)):
        if g["cod_cliente"] not in icli:
            continue
        out.append([icli[g["cod_cliente"]], g["ordine_id"], g["dt_ord"], g["cod_articolo"], g["descrizione"],
                    g["qta_res"], g["imp_res"] or 0, g["dt_cons"] or "",
                    " ".join(x for x in (g["auto_marca"], g["auto_modello"]) if x)])
    return out


def gestionale_al(con):
    """Ultimo giorno dell'export ordini caricato, '' se non c'e'."""
    try:
        return con.execute("SELECT MAX(dt_ord) FROM gestionale_righe").fetchone()[0] or ""
    except sqlite3.OperationalError:
        return ""


def marca(descrizione):
    """"A" Autel, "M" MATE/Huf, "X" altro sensore, None se la riga non conta (kit valvole)."""
    d = (descrizione or "").upper()
    if RE_ESCLUSI.search(d):
        return None
    if RE_AUTEL.search(d):
        return "A"
    if RE_MATE.search(d):
        return "M"
    return "X"


def _righe_sensori(con, dal=PAGINA_DAL):
    """{codice: {id_ordine: [data, {marca: pezzi}]}} per le righe sensore dal `dal`."""
    out = {}
    for r in con.execute("SELECT o.codice_cliente, o.id, o.data_ora, r.descrizione, r.qta FROM righe r"
                         " JOIN ordini o ON o.id=r.ordine_id WHERE r.categoria=? AND o.data_ora >= ? AND COALESCE(o.annullato,0)=0",
                         (CAT_SENSORI, dal)):
        m = marca(r[3])
        if m:
            o = out.setdefault(r[0], {}).setdefault(r[1], [r[2] or "", {}])
            o[1][m] = o[1].get(m, 0) + (r[4] or 0)
    return out


def clienti_sensori(con, dal=PAGINA_DAL):
    return set(_righe_sensori(con, dal))


def colore(ordini):
    """Marca del pallino da {id: [data, {marca: pezzi}]}: quella dell'ultimo ordine con
    Autel o MATE/Huf (piu' pezzi vince, parita' -> MATE); "X" se non ce n'e' nessuno."""
    con_marca = [o for o in ordini.values() if "A" in o[1] or "M" in o[1]]
    if not con_marca:
        return "X"
    ultimo = max(con_marca, key=lambda o: o[0])[1]
    return "A" if ultimo.get("A", 0) > ultimo.get("M", 0) else "M"


def sensori(con, icli, al, dal=PAGINA_DAL):
    """Pallini della mappa: [icli, lat, lng, marca, id ultimo ordine sensori, fermo, approssimata].
    Restituisce anche quanti clienti con sensori non hanno coordinate."""
    per_cliente = _righe_sensori(con, dal)
    coord = coordinate.coordinate(sorted(per_cliente), con)
    limite = ((datetime.date.fromisoformat(al) - datetime.timedelta(days=FERMO_GIORNI)).isoformat()
              if al else "")
    out, senza = [], 0
    for cod, ordini in sorted(per_cliente.items()):
        if cod not in coord or cod not in icli:
            senza += 1
            continue
        lat, lng, appross = coord[cod]
        id_ult, (data_ult, _) = max(ordini.items(), key=lambda kv: kv[1][0])
        out.append([icli[cod], round(lat, 5), round(lng, 5), colore(ordini), id_ult,
                    1 if data_ult[:10] < limite else 0, appross])
    return out, senza


# Telefonate registrate con Plaud (progetto Mak/Plaud Note Pro), già abbinate a un cliente.
# Per ogni telefonata: la scheda del template «Chiamata cliente MAK», sezione per sezione.
# Se l'archivio non c'è, la pagina resta quella dei soli ordini.
CALLREC = os.path.join(os.path.dirname(RADICE), "Plaud Note Pro", "callrec.db")
TITOLI_SCHEDA = [("cliente", "Cliente"), ("interlocutore", "Interlocutore"), ("tipo", "Tipo e richiesta"),
                 ("domande", "Domande e risposte"), ("dati_tecnici", "Dati tecnici"), ("prodotti", "Prodotti e prezzi"),
                 ("obiezioni", "Obiezioni"), ("da_fare", "Cosa devo fare"), ("esito", "Esito"),
                 ("nota_personale", "Nota personale"), ("occasioni", "Occasioni")]


def telefonate(clienti, icli):
    """[indice cliente, data e ora, durata s, titolo, id Plaud senza «of_», [[titolo sezione, testo], …]].
    Aggiunge a `clienti` quelli che hanno telefonate ma nessun ordine dal PAGINA_DAL."""
    if not os.path.exists(CALLREC):
        return []
    sys.path.insert(0, os.path.dirname(CALLREC))
    from callrec import scheda
    tc = sqlite3.connect(f"file:{CALLREC}?mode=ro", uri=True)
    tc.row_factory = sqlite3.Row
    anag = {r["codice"]: r for r in tc.execute("SELECT codice, ragione_sociale, citta, provincia FROM clients")}
    out = []
    for r in tc.execute("SELECT id, title, started_at, duration_s, summary_raw, client_code FROM calls"
                        " WHERE client_code IS NOT NULL AND client_code != '' ORDER BY started_at DESC"):
        cod = r["client_code"]
        if cod not in icli:
            a = anag.get(cod)
            icli[cod] = len(clienti)
            clienti.append([cod, a["ragione_sociale"] if a else cod, (a["citta"] if a else "") or "",
                            (a["provincia"] if a else "") or "", "", 1, "", ""])
        sez = scheda.leggi(r["summary_raw"]) or {}
        out.append([icli[cod], (r["started_at"] or "")[:16].replace("T", " "), r["duration_s"] or 0, r["title"] or "",
                    r["id"][3:] if r["id"].startswith("of_") else r["id"],
                    [[t, sez[k]] for k, t in TITOLI_SCHEDA if sez.get(k)]])
    tc.close()
    return out


# Preventivi della webapp mak-preventivi (tabelle preventivi e preventivi_articoli, vedi data/preventivi.py).
def preventivi(con, clienti, icli):
    """[indice cliente o -1 se da abbinare, data e ora, vettura, esito, [[modello, finitura, misure, netto], …],
    nome scritto nella webapp, data dell'ordine che ha dato l'esito]. Dal più recente.
    Aggiunge a `clienti` quelli che hanno preventivi ma nessun ordine dal PAGINA_DAL."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='preventivi'").fetchone():
        return []
    articoli = {}
    for r in con.execute("SELECT preventivo_id, modello, finitura, misure, netto FROM preventivi_articoli"
                         " ORDER BY preventivo_id, n"):
        articoli.setdefault(r["preventivo_id"], []).append(
            [r["modello"] or "", r["finitura"] or "", r["misure"] or "", r["netto"] or 0])
    out = []
    for r in con.execute("SELECT * FROM preventivi ORDER BY data_ora DESC"):
        cod = r["cliente_codice"] or ""
        if cod and cod not in icli:
            a = con.execute("SELECT ragione_sociale, citta, provincia FROM clienti WHERE codice=?", (cod,)).fetchone()
            icli[cod] = len(clienti)
            clienti.append([cod, (a["ragione_sociale"] if a else r["cliente_nome"]) or cod,
                            (a["citta"] if a else "") or "", (a["provincia"] if a else "") or "", "", 1, "", ""])
        out.append([icli[cod] if cod else -1, (r["data_ora"] or "")[:16].replace("T", " "), r["vettura"] or "",
                    r["esito"] or "in_corso", articoli.get(r["id"], []), r["cliente_nome"] or "",
                    (r["esito_data"] or "")[:10]])
    return out


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
    for segnaposto in ("__PAYLOAD__", "__BUILD_META__", "__LEAFLET_CSS__", "__LEAFLET_JS__"):
        if html.count(segnaposto) != 1:
            sys.exit(f"Il template deve contenere una sola volta {segnaposto}")
    html = html.replace("__PAYLOAD__", payload).replace("__BUILD_META__", json.dumps(meta_pubblica))
    for segnaposto, nome in (("__LEAFLET_CSS__", "leaflet.css"), ("__LEAFLET_JS__", "leaflet.js")):
        with open(os.path.join(VENDOR, nome), encoding="utf-8") as f:
            html = html.replace(segnaposto, f.read())
    with open(USCITA, "w", encoding="utf-8") as f:
        f.write(html)
    if verbose:
        print(f"index.html: {os.path.getsize(USCITA) / 1024:.0f} KB | {d['meta']['ordini']} ordini, "
              f"{d['meta']['clienti']} clienti, {d['meta']['telefonate']} telefonate, periodo {d['meta']['dal']} -> {d['meta']['al']}")
        s = d["meta"]["sens"]
        print(f"mappa sensori: {len(d['sens'])} clienti (Autel {s['A']}, MATE/Huf {s['M']}, altri {s['X']}), "
              f"{s['senza_coord']} senza coordinate")
    return d["meta"]


if __name__ == "__main__":
    build()
