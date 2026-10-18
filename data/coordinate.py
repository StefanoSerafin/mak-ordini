#!/usr/bin/env python3
"""Coordinate dei clienti per la mappa sensori.

    python3 data/coordinate.py --mancanti   # clienti con sensori ancora senza coordinate

Ordine delle fonti, per codice cliente:
  1. il CRM (Mak/mak-crm/index.html, VISIT_MAP_GEODATA e TOOL_MAP_GEODATA): gia'
     controllate, vincono sempre;
  2. la cache locale data/log/coordinate.json (non versionata);
  3. OpenStreetMap Nominatim con indirizzo + CAP + citta' dal DB; se non trova,
     CAP + citta' e poi il solo CAP (il DB tronca alcuni comuni, es. "SANTANGELO
     LODIGIAN"): centro del comune, marcata "approssimata".

Regole Nominatim: una richiesta al secondo, User-Agent riconoscibile, al massimo
MAX_RICHIESTE nuove per esecuzione. Senza rete si ferma e restituisce quello che
ha: il build prosegue e i clienti mancanti arrivano al giro successivo. I "non
trovato" restano in cache e si riprovano dopo RIPROVA_NF_GIORNI.
"""
import datetime
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
DB = os.path.join(QUI, "ordini.db")
CRM = os.path.join(os.path.dirname(RADICE), "mak-crm", "index.html")
CACHE = os.path.join(QUI, "log", "coordinate.json")

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "mak-ordini/1.0 (mappa clienti, uso personale)"
MAX_RICHIESTE = 60
RIPROVA_NF_GIORNI = 30
TIMEOUT = 10


def da_crm():
    """{codice: (lat, lng)} dalle mappe del CRM; vuoto se il file non c'e'."""
    if not os.path.exists(CRM):
        return {}
    with open(CRM, encoding="utf-8") as f:
        html = f.read()
    out = {}
    for nome in ("TOOL_MAP_GEODATA", "VISIT_MAP_GEODATA"):  # la seconda vince se diverse
        m = re.search(r"const " + nome + r"\s*=\s*(\[.*?\]);\s*\n", html, re.S)
        if not m:
            continue
        try:
            righe = json.loads(m.group(1))
        except ValueError:
            continue
        for x in righe:
            cod, lat, lng = str(x.get("COD.") or "").strip(), x.get("lat"), x.get("lng")
            if cod and lat and lng:
                out[cod.zfill(6)] = (float(lat), float(lng))
    return out


def _leggi_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _scrivi_cache(cache):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)


def _cerca(q):
    """q: testo libero, oppure dict di parametri strutturati (es. {"postalcode": "26866"})."""
    par = {"format": "json", "countrycodes": "it", "limit": 1}
    par.update(q if isinstance(q, dict) else {"q": q})
    url = NOMINATIM + "?" + urllib.parse.urlencode(par)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        res = json.load(r)
    return (float(res[0]["lat"]), float(res[0]["lon"])) if res else None


def coordinate(codici, con=None, verbose=False):
    """{codice: (lat, lng, approssimata)} per i codici richiesti che hanno coordinate."""
    crm = da_crm()
    cache = _leggi_cache()
    oggi = datetime.date.today()
    out, da_cercare = {}, []
    for c in codici:
        if c in crm:
            out[c] = (crm[c][0], crm[c][1], 0)
            continue
        v = cache.get(c)
        if v and v.get("fonte") != "nf":
            out[c] = (v["lat"], v["lng"], 1 if v["fonte"] == "comune" else 0)
        elif v and (oggi - datetime.date.fromisoformat(v["data"])).days < RIPROVA_NF_GIORNI:
            continue
        else:
            da_cercare.append(c)
    if not da_cercare:
        return out
    chiudi = con is None
    con = con or sqlite3.connect(DB)
    anag = {r[0]: r[1:] for r in con.execute(
        "SELECT codice, indirizzo, cap, citta, provincia FROM clienti WHERE codice IN (%s)"
        % ",".join("?" * len(da_cercare)), da_cercare)}
    if chiudi:
        con.close()
    richieste, cambiata = 0, False
    for c in da_cercare:
        ind, cap, citta, prov = (x or "" for x in anag.get(c, ("", "", "", "")))
        tentativi = []
        if ind and citta:
            tentativi.append((f"{ind}, {cap} {citta} {prov}".strip(), "indirizzo"))
        if citta:
            tentativi.append((f"{cap} {citta} {prov}".strip(), "comune"))
        if cap:
            tentativi.append(({"postalcode": cap}, "comune"))
        trovato = None
        try:
            for q, fonte in tentativi:
                if richieste >= MAX_RICHIESTE:
                    break
                if richieste:
                    time.sleep(1)
                richieste += 1
                p = _cerca(q)
                if p:
                    trovato = (p, fonte)
                    break
        except OSError as e:  # niente rete o Nominatim non risponde: si riprova al giro dopo
            if verbose:
                print(f"coordinate: geocodifica interrotta ({e})", file=sys.stderr)
            break
        if richieste >= MAX_RICHIESTE and not trovato:
            break
        if trovato:
            (lat, lng), fonte = trovato
            cache[c] = {"lat": round(lat, 5), "lng": round(lng, 5), "fonte": fonte, "data": oggi.isoformat()}
            out[c] = (cache[c]["lat"], cache[c]["lng"], 1 if fonte == "comune" else 0)
        else:
            cache[c] = {"fonte": "nf", "data": oggi.isoformat()}
        cambiata = True
        if verbose:
            print(f"  {c} {citta}: {trovato[1] if trovato else 'non trovato'}")
    if cambiata:
        _scrivi_cache(cache)
    return out


if __name__ == "__main__":
    if "--mancanti" not in sys.argv:
        sys.exit(__doc__)
    sys.path.insert(0, QUI)
    import build
    con = sqlite3.connect(DB)
    codici = sorted(build.clienti_sensori(con))
    trovate = coordinate(codici, con, verbose=True)
    nomi = dict(con.execute("SELECT codice, ragione_sociale || ' - ' || IFNULL(citta,'') FROM clienti"))
    mancanti = [c for c in codici if c not in trovate]
    print(f"{len(codici)} clienti con sensori, {len(trovate)} con coordinate, {len(mancanti)} senza")
    for c in mancanti:
        print(f"  {c} {nomi.get(c, '')}")
