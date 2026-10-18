#!/usr/bin/env python3
"""Coordinate dei clienti per la mappa sensori.

    python3 data/coordinate.py --verifica          # verifica con Google i clienti non ancora verificati
    python3 data/coordinate.py --verifica --tutti  # rifà la verifica di tutti (costa chiamate Google)
    python3 data/coordinate.py --mancanti          # clienti con sensori ancora senza coordinate
    python3 data/coordinate.py --ridecidi          # rifà le scelte dai dati Google salvati (gratis)

Ordine delle fonti, per codice cliente:
  1. correzioni a mano in data/log/coordinate_manuali.json ({codice: {"lat", "lng", "nota"}};
     con "provvisorio": true il punto resta tratteggiato e nell'elenco da controllare);
  2. verifica Google salvata in cache (data/log/coordinate.json, fonte "google-…");
  3. se c'e' la chiave Google, verifica dei clienti nuovi (massimo MAX_RICHIESTE per giro);
  4. senza chiave: coordinate del CRM, poi OpenStreetMap Nominatim (vecchio metodo, impreciso).

Verifica Google di un cliente (scelta di Stefano, 2026-10-18: vale dove sta l'officina):
  - geocodifica l'indirizzo dell'ordine B2B e, se diverso, quello del CRM (Geocoding API);
  - cerca l'attivita' per ragione sociale + citta' (Places Text Search, solo campi
    id/nome/indirizzo/posizione = fascia Pro, non Enterprise come il giro nuove aperture);
  - "ok" (punto dell'attivita' Google), in quest'ordine: stesso nome e stessa via + civico
    (dell'ordine o del CRM); attivita' entro SOGLIA_M; stesso nome entro SOGLIA_NOME_M; stesso
    nome nello stesso comune. Il CAP del DB e' spesso quello vecchio (20090, 20010...) e Google
    Geocoding sbaglia comune: per questo si confronta il testo dell'indirizzo, non solo la distanza;
  - "ok" (indirizzo dell'ordine): nessun omonimo entro SOGLIA_OMONIMI_M, indirizzo preciso al
    civico e nel comune giusto, CRM d'accordo;
  - altrimenti "controllare": punto provvisorio (bordo tratteggiato sulla mappa) e il cliente
    finisce in data/log/coordinate_da_controllare.md con i candidati e i link a Google Maps.

Chiave: GOOGLE_MAPS_API_KEY da ambiente o da Mak/nuove-aperture/.env (progetto Cloud "MAK CRM").
Tutti i file in data/log/ restano sul Mac (non versionati).
"""
import datetime
import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
MAK = os.path.dirname(RADICE)
DB = os.path.join(QUI, "ordini.db")
CRM = os.path.join(MAK, "mak-crm", "index.html")
ENV_CHIAVE = os.path.join(MAK, "nuove-aperture", ".env")
CACHE = os.path.join(QUI, "log", "coordinate.json")
MANUALI = os.path.join(QUI, "log", "coordinate_manuali.json")
DA_CONTROLLARE = os.path.join(QUI, "log", "coordinate_da_controllare.md")

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_CAMPI = "places.id,places.displayName,places.formattedAddress,places.location"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "mak-ordini/1.0 (mappa clienti, uso personale)"
MAX_RICHIESTE = 60       # clienti nuovi verificati per giro automatico
SOGLIA_M = 300           # officina Google e indirizzo "concordano" sotto questa distanza
SOGLIA_NOME_M = 1500     # stesso nome: accettata fino a questa distanza dall'indirizzo
SOGLIA_OMONIMI_M = 10000 # stesso nome oltre questa distanza: e' un'altra attivita'
PRECISI = {"ROOFTOP", "RANGE_INTERPOLATED"}
TIMEOUT = 15
# parole che non distinguono un'attivita' dall'altra nel confronto dei nomi
PAROLE_VUOTE = {"SRL", "SRLS", "SNC", "SAS", "SPA", "S.R.L.", "S.N.C.", "S.A.S.", "DI", "DEI", "DEL", "DELLA",
                "E", "C.", "&", "AUTO", "GOMME", "SERVICE", "SERVIZI", "AUTOFFICINA", "OFFICINA", "CARROZZERIA",
                "PNEUMATICI", "GOMMISTA", "CAR", "CARS", "MOTORS", "GROUP", "SOCIETA", "UNIPERSONALE", "IN", "ACCOMANDITA",
                "RICAMBI", "AUTORICAMBI", "ACCESSORI", "TYRE", "TYRES", "PNEUS", "MOTO", "CENTRO", "ITALIA",
                "ELETTRAUTO", "AUTORIPARAZIONI", "SERVIZIO", "GOMMISTI", "AUTOSERVICE", "NUOVA", "SOCIO", "UNICO",
                "UNINOMINALE", "STAZIONE", "SERVICES", "DIESEL", "GARAGE"}


# ---------------------------------------------------------------- utilità
def _leggi(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _scrivi(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True)


def distanza_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def parole(nome):
    return {w for w in re.split(r"[^A-Z0-9&.]+", (nome or "").upper()) if len(w) >= 3 and w not in PAROLE_VUOTE}


def chiave_google():
    k = os.environ.get("GOOGLE_MAPS_API_KEY")
    if k:
        return k
    try:
        with open(ENV_CHIAVE, encoding="utf-8") as f:
            for r in f:
                if r.strip().startswith("GOOGLE_MAPS_API_KEY="):
                    return r.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def _norm_ind(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def da_crm():
    """{codice: {"lat", "lng", "ind", "cap", "citta", "prov"}} dalle mappe del CRM."""
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
            cod = str(x.get("COD.") or "").strip()
            if cod:
                out[cod.zfill(6)] = {"lat": x.get("lat"), "lng": x.get("lng"), "ind": x.get("INDIRIZZO") or "",
                                     "cap": x.get("CAP") or "", "citta": x.get("CITTA'") or "", "prov": x.get("PR") or ""}
    return out


# ---------------------------------------------------------------- Google
class Google:
    def __init__(self, key):
        self.key, self.n_geo, self.n_places = key, 0, 0

    def geocodifica(self, indirizzo):
        """(lat, lng, location_type, indirizzo formattato) oppure None."""
        q = urllib.parse.urlencode({"address": indirizzo, "key": self.key, "language": "it",
                                    "region": "it", "components": "country:IT"})
        with urllib.request.urlopen(GEOCODE_URL + "?" + q, timeout=TIMEOUT) as r:
            j = json.load(r)
        self.n_geo += 1
        if j.get("status") not in ("OK", "ZERO_RESULTS"):
            raise OSError(f"Geocoding: {j.get('status')} {j.get('error_message', '')}")
        if not j.get("results"):
            return None
        g = j["results"][0]
        loc = g["geometry"]["location"]
        return (loc["lat"], loc["lng"], g["geometry"].get("location_type", ""), g.get("formatted_address", ""))

    def cerca_attivita(self, testo, centro=None):
        corpo = {"textQuery": testo, "languageCode": "it", "regionCode": "it", "pageSize": 5}
        if centro:
            corpo["locationBias"] = {"circle": {"center": {"latitude": centro[0], "longitude": centro[1]},
                                                "radius": 5000.0}}
        req = urllib.request.Request(PLACES_URL, data=json.dumps(corpo).encode(), method="POST", headers={
            "Content-Type": "application/json", "X-Goog-Api-Key": self.key, "X-Goog-FieldMask": PLACES_CAMPI})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            j = json.load(r)
        self.n_places += 1
        return [{"nome": p.get("displayName", {}).get("text", ""), "ind": p.get("formattedAddress", ""),
                 "lat": p["location"]["latitude"], "lng": p["location"]["longitude"]}
                for p in j.get("places", []) if p.get("location")]


def _lettere(s):
    return re.sub(r"[^A-Z]", "", (s or "").upper())


PAROLE_VIA = {"VIA", "VIALE", "PIAZZA", "PIAZZALE", "CORSO", "STRADA", "LARGO", "VICOLO", "STATALE", "PROV",
              "PROVINCIALE", "LOC", "LOCALITA", "FRAZ", "FRAZIONE", "PRIVATA", "STR", "SNC"}


def _indirizzo_coincide(ind, testo):
    """Stessa via e stesso civico (il CAP del DB e' spesso quello vecchio, il comune no)."""
    if not ind:
        return False
    numeri = re.findall(r"\d+", ind)
    vie = [w for w in re.split(r"[^A-Z]+", ind.upper()) if len(w) >= 4 and w not in PAROLE_VIA]
    t = (testo or "").upper()
    return bool(numeri and vie) and numeri[0] in re.findall(r"\d+", t) and any(w in t for w in vie)


def _comune_coincide(citta, cap, testo):
    """Il nome del comune (o della frazione) compare nell'indirizzo. Il CAP no: e' condiviso
    tra comuni (74020 = Maruggio e Lizzano) e nel DB e' spesso quello vecchio."""
    c, t = _lettere(citta), _lettere(testo)
    if not c:
        return False
    if c[:10] in t:
        return True
    # parola per parola, anche troncate: "BESANA BRIANZA" ~ "Besana in Brianza", "S.ANGELO LODIGIAN"
    pc = [w for w in re.split(r"[^A-Z]+", citta.upper()) if len(w) >= 4]
    pt = re.split(r"[^A-Z]+", (testo or "").upper())
    return bool(pc) and all(any(len(y) >= 4 and (x.startswith(y) or y.startswith(x)) for y in pt) for x in pc)


def simile(nome, altro):
    a, b = parole(nome), parole(altro)
    return bool(a & b) or any(min(len(x), len(y)) >= 6 and (x.startswith(y) or y.startswith(x)) for x in a for y in b)


def verifica_cliente(g, cod, anag, crm):
    """Chiede a Google indirizzi e attività, poi decide (dict da salvare in cache)."""
    nome, ind, cap, citta, prov = anag
    indirizzi = []
    if ind or citta:
        indirizzi.append(("ordine", f"{ind}, {cap} {citta} {prov}, Italia".strip(", ")))
    if crm and crm.get("ind") and _norm_ind(crm["ind"]) != _norm_ind(ind):
        indirizzi.append(("CRM", f"{crm['ind']}, {crm['cap']} {crm['citta']} {crm['prov']}, Italia"))
    geo = {}
    for chi, testo in indirizzi:
        r = g.geocodifica(testo)
        if r:
            geo[chi] = {"lat": r[0], "lng": r[1], "tipo": r[2], "ind": r[3], "cercato": testo}
    centro = next(((v["lat"], v["lng"]) for v in geo.values()), None)
    luogo = crm.get("citta") if crm and not citta else citta
    posti = g.cerca_attivita(f"{nome} {luogo or ''} {prov or ''}".strip(), centro)
    esito = {"data": datetime.date.today().isoformat(), "nome": nome, "indirizzi": geo, "posti": posti[:5]}
    return decidi(esito, anag, crm)


def decidi(esito, anag, crm):
    """Sceglie il punto dai dati Google gia' raccolti (si puo' rifare senza nuove chiamate).
    Vale dove sta l'officina (scelta di Stefano, 2026-10-18)."""
    nome, ind, cap, citta, _ = anag
    geo, posti = esito.get("indirizzi", {}), esito.get("posti", [])
    for k in ("lat", "lng", "motivo"):
        esito.pop(k, None)
    rif = [(ind, cap, citta)] + ([(crm.get("ind"), str(crm.get("cap") or ""), crm.get("citta"))] if crm else [])
    for p in posti:
        p["dist"] = {chi: round(distanza_m((p["lat"], p["lng"]), (v["lat"], v["lng"]))) for chi, v in geo.items()}
        p["vicino"] = min(p["dist"].values()) if p["dist"] else None
        p["simile"] = simile(nome, p["nome"])
        p["stesso_ind"] = any(_indirizzo_coincide(i, p["ind"]) for i, _, _ in rif)
        p["stesso_comune"] = any(_comune_coincide(ci, ca, p["ind"]) for _, ca, ci in rif)

    def ok(p, motivo, fonte="google-officina"):
        esito.update(lat=p["lat"], lng=p["lng"], fonte=fonte, stato="ok", motivo=motivo)
        return esito

    regole = [
        (lambda p: p["simile"] and p["stesso_ind"] and (p["stesso_comune"] or (p["vicino"] or 1e9) <= SOGLIA_NOME_M),
         "stesso nome e stesso indirizzo"),
        (lambda p: p["vicino"] is not None and p["vicino"] <= SOGLIA_M and (p["simile"] or p["stesso_ind"]),
         "officina a meno di %d m dall'indirizzo" % SOGLIA_M),
        (lambda p: p["simile"] and p["vicino"] is not None and p["vicino"] <= SOGLIA_NOME_M,
         "stesso nome a meno di %d m dall'indirizzo" % SOGLIA_NOME_M),
        (lambda p: p["simile"] and p["stesso_comune"], "stesso nome, stesso comune"),
        (lambda p: p["stesso_ind"] and p["stesso_comune"], "stessa via, civico e comune"),
        (lambda p: p["stesso_comune"] and p["vicino"] is not None and p["vicino"] <= SOGLIA_M,
         "attività nello stesso comune a meno di %d m dall'indirizzo" % SOGLIA_M),
    ]
    for regola, motivo in regole:
        trovati = sorted([p for p in posti if regola(p)], key=lambda p: (p["vicino"] is None, p["vicino"] or 0))
        if trovati:
            return ok(trovati[0], f"{motivo}: «{trovati[0]['nome']}», {trovati[0]['ind']}")
    # omonimi a piu' di SOGLIA_OMONIMI_M non sono il cliente
    simili = [p for p in posti if p["simile"] and (p["vicino"] is None or p["vicino"] <= SOGLIA_OMONIMI_M)]
    go = geo.get("ordine")
    crm_ok = "CRM" not in geo or distanza_m((go["lat"], go["lng"]), (geo["CRM"]["lat"], geo["CRM"]["lng"])) <= SOGLIA_M \
        if go else False
    if go and go["tipo"] in PRECISI and not simili and crm_ok and _comune_coincide(citta, "", go["ind"]):
        return ok(go, f"indirizzo dell'ordine preciso al civico: {go['ind']}", fonte="google-indirizzo")
    # da controllare: punto provvisorio = attività con nome simile, poi indirizzo più preciso
    esito.update(fonte="google-provvisorio", stato="controllare")
    if simili:
        p = simili[0]
        esito.update(lat=p["lat"], lng=p["lng"], motivo=f"su Google «{p['nome']}» ({p['ind']}) non coincide con gli indirizzi")
    else:
        migliore = sorted(geo.values(), key=lambda v: v["tipo"] not in PRECISI)
        if migliore:
            esito.update(lat=migliore[0]["lat"], lng=migliore[0]["lng"],
                         motivo="nessuna attività riconoscibile su Google e indirizzi poco precisi o discordi")
        else:
            esito.update(motivo="nessun risultato Google")
    return esito


def ridecidi(con, verbose=False):
    """Rifà la scelta su tutta la cache Google, senza chiamate (dopo aver cambiato le regole)."""
    cache, crm = _leggi(CACHE), da_crm()
    codici = [c for c, v in cache.items() if str(v.get("fonte", "")).startswith("google")]
    anag = _anagrafica(con, codici)
    for c in codici:
        if c in anag:
            prima = cache[c].get("stato")
            decidi(cache[c], anag[c], crm.get(c))
            if verbose and prima != cache[c]["stato"]:
                print(f"  {c} {anag[c][0][:40]:40} {prima} -> {cache[c]['stato']}: {cache[c].get('motivo', '')}")
    _scrivi(CACHE, cache)


# ---------------------------------------------------------------- Nominatim (senza chiave)
def _nominatim(q):
    par = {"format": "json", "countrycodes": "it", "limit": 1}
    par.update(q if isinstance(q, dict) else {"q": q})
    req = urllib.request.Request(NOMINATIM + "?" + urllib.parse.urlencode(par), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        res = json.load(r)
    return (float(res[0]["lat"]), float(res[0]["lon"])) if res else None


def _osm(anag):
    _, ind, cap, citta, prov = anag
    tentativi = []
    if ind and citta:
        tentativi.append((f"{ind}, {cap} {citta} {prov}".strip(), "osm-indirizzo"))
    if citta:
        tentativi.append((f"{cap} {citta} {prov}".strip(), "osm-comune"))
    if cap:
        tentativi.append(({"postalcode": cap}, "osm-comune"))
    for q, fonte in tentativi:
        time.sleep(1)
        p = _nominatim(q)
        if p:
            return {"lat": p[0], "lng": p[1], "fonte": fonte, "stato": "controllare" if fonte == "osm-comune" else "osm",
                    "data": datetime.date.today().isoformat()}
    return None


# ---------------------------------------------------------------- API per build.py
def _anagrafica(con, codici):
    if not codici:
        return {}
    return {r[0]: tuple(x or "" for x in r[1:]) for r in con.execute(
        "SELECT codice, ragione_sociale, indirizzo, cap, citta, provincia FROM clienti WHERE codice IN (%s)"
        % ",".join("?" * len(codici)), list(codici))}


def verifica(codici, con, tutti=False, limite=None, verbose=False):
    """Verifica con Google i codici senza esito Google in cache (o tutti). Aggiorna la cache."""
    key = chiave_google()
    if not key:
        if verbose:
            print("coordinate: manca GOOGLE_MAPS_API_KEY, verifica saltata", file=sys.stderr)
        return 0
    cache, crm, g = _leggi(CACHE), da_crm(), Google(key)
    fare = [c for c in codici if tutti or not str(cache.get(c, {}).get("fonte", "")).startswith("google")]
    if limite is not None:
        fare = fare[:limite]
    anag = _anagrafica(con, fare)
    fatti = 0
    try:
        for i, c in enumerate(fare, 1):
            if c not in anag:
                continue
            cache[c] = verifica_cliente(g, c, anag[c], crm.get(c))
            fatti += 1
            if verbose:
                e = cache[c]
                print(f"  [{i}/{len(fare)}] {c} {anag[c][0][:40]:40} {e['stato']:11} {e.get('motivo', '')}")
            if fatti % 25 == 0:
                _scrivi(CACHE, cache)
    except OSError as e:  # rete o quota: si salva quello che c'e', il resto al giro dopo
        print(f"coordinate: verifica interrotta ({e})", file=sys.stderr)
    _scrivi(CACHE, cache)
    if verbose:
        print(f"chiamate Google: {g.n_geo} Geocoding, {g.n_places} Places Text Search (Pro)")
    return fatti


def coordinate(codici, con=None, verbose=False):
    """{codice: (lat, lng, approssimata)}. approssimata = 1 se il punto va ancora controllato."""
    chiudi = con is None
    con = con or sqlite3.connect(DB)
    try:
        verifica(codici, con, limite=MAX_RICHIESTE, verbose=verbose)
        cache, manuali = _leggi(CACHE), _leggi(MANUALI)
        crm = None
        out, osm_fatti, cambiata = {}, 0, False
        for c in codici:
            if c in manuali:
                out[c] = (manuali[c]["lat"], manuali[c]["lng"], 1 if manuali[c].get("provvisorio") else 0)
                continue
            v = cache.get(c)
            if v and v.get("lat") is not None:
                out[c] = (v["lat"], v["lng"], 0 if v.get("stato") in ("ok", "osm") else 1)
                continue
            # senza verifica Google: CRM, poi OpenStreetMap
            crm = crm if crm is not None else da_crm()
            if c in crm and crm[c]["lat"]:
                out[c] = (float(crm[c]["lat"]), float(crm[c]["lng"]), 1)
                continue
            if osm_fatti < MAX_RICHIESTE:
                a = _anagrafica(con, [c]).get(c)
                try:
                    r = _osm(a) if a else None
                except OSError:
                    r, osm_fatti = None, MAX_RICHIESTE
                osm_fatti += 1
                if r:
                    cache[c], cambiata = r, True
                    out[c] = (r["lat"], r["lng"], 0 if r["stato"] == "osm" else 1)
        if cambiata:
            _scrivi(CACHE, cache)
        return out
    finally:
        if chiudi:
            con.close()


def scrivi_da_controllare(codici):
    """Elenco locale dei clienti da controllare, con i candidati e i link a Google Maps."""
    cache, manuali = _leggi(CACHE), _leggi(MANUALI)
    righe = [c for c in codici if c not in manuali and cache.get(c, {}).get("stato") == "controllare"]
    provvisori = [c for c in codici if manuali.get(c, {}).get("provvisorio")]
    mappa = lambda la, lo: f"https://www.google.com/maps?q={la:.6f},{lo:.6f}"
    t = [f"# Coordinate da controllare ({len(righe) + len(provvisori)})", "",
         f"Generato il {datetime.date.today().isoformat()} da `data/coordinate.py`. Per correggere un punto: "
         "aggiungi il cliente in `data/log/coordinate_manuali.json` come "
         '`"012345": {"lat": 45.1, "lng": 9.2, "nota": "…"}` e rifai il build.', ""]
    for c in provvisori:
        e = manuali[c]
        t += [f"## {cache.get(c, {}).get('nome', c)} ({c}) — punto provvisorio a mano", f"- {e.get('nota', '')}",
              f"- Punto attuale: [mappa]({mappa(e['lat'], e['lng'])})", ""]
    for c in sorted(righe, key=lambda c: cache[c].get("nome", "")):
        e = cache[c]
        t.append(f"## {e.get('nome', '')} ({c})")
        t.append(f"- Motivo: {e.get('motivo', '')}")
        if e.get("lat") is not None:
            t.append(f"- Punto provvisorio: [mappa]({mappa(e['lat'], e['lng'])})")
        for chi, v in e.get("indirizzi", {}).items():
            t.append(f"- Indirizzo {chi}: {v['cercato']} → {v['ind']} ({v['tipo']}) [mappa]({mappa(v['lat'], v['lng'])})")
        for p in e.get("posti", []):
            d = ", ".join(f"{k} {v} m" for k, v in p.get("dist", {}).items())
            t.append(f"- Google: «{p['nome']}» — {p['ind']} ({d}) [mappa]({mappa(p['lat'], p['lng'])})")
        t.append("")
    os.makedirs(os.path.dirname(DA_CONTROLLARE), exist_ok=True)
    with open(DA_CONTROLLARE, "w", encoding="utf-8") as f:
        f.write("\n".join(t))
    return len(righe) + len(provvisori)


if __name__ == "__main__":
    if not ({"--mancanti", "--verifica", "--ridecidi"} & set(sys.argv)):
        sys.exit(__doc__)
    sys.path.insert(0, QUI)
    import build
    con = sqlite3.connect(DB)
    codici = sorted(build.clienti_sensori(con))
    if "--ridecidi" in sys.argv:
        ridecidi(con, verbose=True)
    if "--verifica" in sys.argv:
        verifica(codici, con, tutti="--tutti" in sys.argv, verbose=True)
    trovate = coordinate(codici, con)
    cache = _leggi(CACHE)
    stati = {}
    for c in codici:
        s = "manuale" if c in _leggi(MANUALI) else cache.get(c, {}).get("stato", "senza verifica")
        stati[s] = stati.get(s, 0) + 1
    n = scrivi_da_controllare(codici)
    print(f"{len(codici)} clienti con sensori, {len(trovate)} con coordinate; stati: {stati}")
    print(f"da controllare: {n} -> {os.path.relpath(DA_CONTROLLARE, RADICE)}")
    nomi = dict(con.execute("SELECT codice, ragione_sociale || ' - ' || IFNULL(citta,'') FROM clienti"))
    for c in codici:
        if c not in trovate:
            print(f"  senza coordinate: {c} {nomi.get(c, '')}")
