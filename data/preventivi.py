"""Preventivi della webapp mak-preventivi nel database ordini (dal 2026-10-24).

    python3 data/preventivi.py clienti     # file madre -> Mak/mak-preventivi-dati/clienti.json (push se cambiato)
    python3 data/preventivi.py importa     # pull dell'archivio -> tabelle preventivi e preventivi_articoli
    python3 data/preventivi.py esiti       # confronto con gli ordini dei 30 giorni dopo
    python3 data/preventivi.py riepilogo   # tabella per mese ed esito, a terminale
    python3 data/preventivi.py notte       # importa + esiti (lo lancia notturno.sh)

Archivio: repo privato StefanoSerafin/mak-preventivi-dati, clonato in Mak/mak-preventivi-dati. La webapp ci scrive un
file per preventivo (preventivi/AAAA/MM/<id>.json); il Mac ci scrive l'elenco clienti per il campo «Cliente».

Regole dell'esito (piano 2026-10-24, scelte di Stefano), sugli ordini del cliente nei 30 giorni dopo il preventivo,
chiunque li abbia inseriti:
  riuscito              una riga con lo stesso codice articolo di una ruota proposta
  riuscito_altra_ruota  nessuna, ma una ruota (lega o acciaio) dello stesso diametro di una proposta
  non_riuscito          nessuno dei due e sono passati 30 giorni
  in_corso              negli altri casi
  da_abbinare           preventivo senza codice cliente
Questo repo è pubblico: qui solo codice, nessun dato di clienti. Funziona con il Python 3.9 di sistema.
"""
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(QUI, "ordini.db")
MADRE = os.path.normpath(os.path.join(QUI, "..", "..", "MAK 2026.xlsx"))
ARCHIVIO = os.path.normpath(os.path.join(QUI, "..", "..", "mak-preventivi-dati"))
ABBINAMENTI = os.path.join(QUI, "log", "preventivi_abbinamenti.json")
GIORNI = 30
CATEGORIE_RUOTE = ("Ruote lega", "Ruote acciaio")
# solo queste colonne del file madre escono dal Mac: mai ID, PWD, CELL, EMAIL
COLONNE_MADRE = {"COD.": "codice", "CLIENTE": "nome", "LISTINO 26": "listino", "NETWORK": "network"}


def apri(percorso=DB):
    con = sqlite3.connect(percorso)
    con.row_factory = sqlite3.Row
    with open(os.path.join(QUI, "schema.sql"), encoding="utf-8") as f:
        con.executescript(f.read())
    return con


def codice6(v):
    s = re.sub(r"\D", "", str(v if v is not None else "").split(".")[0])
    return s.zfill(6) if s else ""


def normalizza_nome(s):
    """Per abbinare i nomi scritti a mano: minuscole, senza punteggiatura né forme societarie."""
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    togli = {"srl", "srls", "snc", "sas", "spa", "s", "r", "l", "n", "c", "di", "e", "ditta", "f", "lli", "fratelli"}
    return " ".join(p for p in s.split() if p not in togli)


def _git(*args):
    return subprocess.run(["git", "-C", ARCHIVIO] + list(args), capture_output=True, text=True)


# ---------- clienti: file madre -> clienti.json ----------

def leggi_madre(percorso=MADRE):
    import openpyxl
    wb = openpyxl.load_workbook(percorso, read_only=True, data_only=True)
    ws = wb["Clienti"]
    righe = ws.iter_rows(values_only=True)
    testa = [str(c).strip() if c is not None else "" for c in next(righe)]
    mancanti = [c for c in COLONNE_MADRE if c not in testa]
    if mancanti:
        raise SystemExit(f"Nel file madre mancano le colonne {mancanti}: mi fermo.")
    pos = {campo: testa.index(col) for col, campo in COLONNE_MADRE.items()}
    clienti, visti = [], set()
    for r in righe:
        if not r:
            continue
        codice = codice6(r[pos["codice"]])
        nome = str(r[pos["nome"]] or "").strip()
        if not codice or not nome or codice in visti:
            continue
        visti.add(codice)
        clienti.append({"codice": codice, "nome": nome,
                        "listino": str(r[pos["listino"]] or "").strip(),
                        "network": str(r[pos["network"]] or "").strip()})
    wb.close()
    return sorted(clienti, key=lambda c: c["nome"].upper())


def clienti_solo_ordini(madre, percorso_db=DB):
    """Clienti con ordini B2B ma assenti dal file madre (es. ordini inseriti dalla sede): nome dal database ordini."""
    if not os.path.exists(percorso_db):
        return []
    noti = {c["codice"] for c in madre}
    con = sqlite3.connect(f"file:{percorso_db}?mode=ro", uri=True)
    righe = con.execute("SELECT codice, ragione_sociale, network, '' FROM clienti").fetchall()
    # anagrafica del gestionale (export del lunedi', dal 2026-10-28): clienti che il file madre non ha,
    # con il codice listino (prima parola, es. "SD"). Per i clienti del file madre vale il suo LISTINO 26:
    # su molti clienti i due non coincidono (SQ nel file madre, SD nel gestionale), decide Stefano.
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='anagrafica_b2b'").fetchone():
        righe = con.execute("SELECT codice, ragione_sociale, network, listino FROM anagrafica_b2b").fetchall() + righe
    con.close()
    out, visti = [], set(noti)
    for c, n, net, lst in righe:
        c = codice6(c)
        if c and c not in visti and (n or "").strip():
            visti.add(c)
            out.append({"codice": c, "nome": (n or "").strip(), "listino": (lst or "").split()[0] if (lst or "").strip() else "",
                        "network": (net or "").strip()})
    return out


def esporta_clienti(git=True):
    clienti = leggi_madre()
    clienti = sorted(clienti + clienti_solo_ordini(clienti), key=lambda c: c["nome"].upper())
    testo = json.dumps(clienti, ensure_ascii=False, indent=0) + "\n"
    dest = os.path.join(ARCHIVIO, "clienti.json")
    if git:
        _git("pull", "-q", "--rebase")
    vecchio = open(dest, encoding="utf-8").read() if os.path.exists(dest) else ""
    if testo == vecchio:
        print(f"clienti.json invariato ({len(clienti)} clienti)")
        return len(clienti)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(testo)
    print(f"clienti.json aggiornato: {len(clienti)} clienti")
    if git:
        _git("add", "clienti.json")
        _git("commit", "-q", "-m", "clienti aggiornati dal file madre")
        r = _git("push", "-q")
        if r.returncode:
            print("push di clienti.json non riuscito:", r.stderr.strip())
    return len(clienti)


# ---------- importa: archivio -> database ----------

def _clienti_archivio():
    try:
        with open(os.path.join(ARCHIVIO, "clienti.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _abbinamenti():
    try:
        with open(ABBINAMENTI, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def leggi_archivio(cartella=None):
    cartella = cartella or os.path.join(ARCHIVIO, "preventivi")
    out = []
    for radice, _, files in os.walk(cartella):
        for nome in sorted(files):
            if nome.endswith(".json"):
                try:
                    with open(os.path.join(radice, nome), encoding="utf-8") as f:
                        out.append(json.load(f))
                except (OSError, ValueError) as e:
                    print(f"file saltato {nome}: {e}")
    return out


def carica(con, preventivi, clienti=None, abbinamenti=None):
    """Upsert dei preventivi nel database. Ritorna (nuovi, aggiornati, da_abbinare)."""
    clienti = clienti if clienti is not None else _clienti_archivio()
    abbinamenti = abbinamenti if abbinamenti is not None else _abbinamenti()
    per_nome = {}
    for c in clienti:
        chiave = normalizza_nome(c["nome"])
        if chiave:  # un nome che dopo la pulizia resta vuoto non può abbinare niente
            per_nome.setdefault(chiave, []).append(c["codice"])
    adesso = dt.datetime.now().isoformat(timespec="seconds")
    nuovi = aggiornati = da_abbinare = 0
    with con:
        for p in preventivi:
            pid = p.get("id")
            if not pid:
                continue
            codice, come = codice6(p.get("cliente_codice")), "app" if p.get("cliente_codice") else ""
            if pid in abbinamenti:
                codice, come = codice6(abbinamenti[pid]), "manuale"
            elif not codice and normalizza_nome(p.get("cliente_nome")):
                trovati = per_nome.get(normalizza_nome(p.get("cliente_nome")), [])
                if len(trovati) == 1:
                    codice, come = trovati[0], "nome"
            if not codice:
                da_abbinare += 1
            v = p.get("vettura") or {}
            articoli = p.get("articoli") or []
            diametri = sorted({str(a.get("diametro") or "") for a in articoli if a.get("diametro")})
            esiste = con.execute("SELECT 1 FROM preventivi WHERE id=?", (pid,)).fetchone()
            nuovi += not esiste
            aggiornati += bool(esiste)
            con.execute("""INSERT OR REPLACE INTO preventivi
                (id, data_ora, cliente_codice, cliente_nome, abbinato, vettura, vettura_json, diametri, listino, tpms,
                 esito, esito_ordine, esito_data, importato)
                VALUES (?,?,?,?,?,?,?,?,?,?,
                        (SELECT esito FROM preventivi WHERE id=?), (SELECT esito_ordine FROM preventivi WHERE id=?),
                        (SELECT esito_data FROM preventivi WHERE id=?), ?)""",
                        (pid, p.get("data_ora"), codice, p.get("cliente_nome") or "", come,
                         v.get("testo") or " ".join(x for x in (v.get("marca"), v.get("modello")) if x),
                         json.dumps(v, ensure_ascii=False), ",".join(diametri), p.get("listino") or "",
                         json.dumps(p["tpms"], ensure_ascii=False) if p.get("tpms") else "",
                         pid, pid, pid, adesso))
            con.execute("DELETE FROM preventivi_articoli WHERE preventivo_id=?", (pid,))
            for n, a in enumerate(articoli, 1):
                con.execute("""INSERT INTO preventivi_articoli VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (pid, n, a.get("codiceArticolo") or a.get("code"), a.get("code"), a.get("tipo"),
                             a.get("modello"), a.get("finitura"), a.get("misure"), str(a.get("diametro") or ""),
                             a.get("netto"), a.get("listinoPubblico"), a.get("accessori")))
    return nuovi, aggiornati, da_abbinare


def togli_mancanti(con, preventivi):
    """L'archivio è la fonte: i preventivi tolti dall'archivio (es. prove cancellate) escono anche dal database."""
    presenti = {p.get("id") for p in preventivi}
    via = [r[0] for r in con.execute("SELECT id FROM preventivi") if r[0] not in presenti]
    with con:
        for pid in via:
            con.execute("DELETE FROM preventivi_articoli WHERE preventivo_id=?", (pid,))
            con.execute("DELETE FROM preventivi WHERE id=?", (pid,))
    return len(via)


def importa(con, git=True):
    if git:
        r = _git("pull", "-q", "--rebase")
        if r.returncode:
            print("pull dell'archivio non riuscito, uso la copia locale:", r.stderr.strip())
    archivio = leggi_archivio()
    if not os.path.isdir(os.path.join(ARCHIVIO, "preventivi")):
        print(f"archivio non trovato in {ARCHIVIO}: niente da importare")
        return
    nuovi, aggiornati, da_abbinare = carica(con, archivio)
    tolti = togli_mancanti(con, archivio)
    print(f"preventivi: {nuovi} nuovi, {aggiornati} aggiornati, {tolti} tolti, {da_abbinare} da abbinare")


# ---------- esiti ----------

def diametro_descrizione(descrizione):
    """'6,5J16 APOLL/BGY ET32 ...' -> '16'"""
    m = re.search(r"J(\d{2})\b", descrizione or "")
    return m.group(1) if m else ""


def calcola_esiti(con, oggi=None):
    oggi = oggi or dt.date.today()
    conta = {}
    with con:
        for p in con.execute("SELECT id, data_ora, cliente_codice, diametri FROM preventivi").fetchall():
            esito, ordine, quando = "da_abbinare", None, None
            if p["cliente_codice"]:
                inizio = dt.datetime.fromisoformat(p["data_ora"][:19])
                fine = inizio + dt.timedelta(days=GIORNI)
                codici = {r[0] for r in con.execute(
                    "SELECT codice_articolo FROM preventivi_articoli WHERE preventivo_id=? AND codice_articolo<>''",
                    (p["id"],))}
                diametri = set(filter(None, (p["diametri"] or "").split(",")))
                righe = con.execute(
                    """SELECT o.id, o.data_ora, r.cod_articolo, r.descrizione, r.categoria
                       FROM ordini o JOIN righe r ON r.ordine_id = o.id
                       WHERE o.codice_cliente=? AND o.data_ora > ? AND o.data_ora <= ?
                       ORDER BY o.data_ora""",
                    (p["cliente_codice"], inizio.isoformat(sep=" "), fine.isoformat(sep=" "))).fetchall()
                stesso = next((r for r in righe if r["cod_articolo"] in codici), None)
                altra = next((r for r in righe if r["categoria"] in CATEGORIE_RUOTE
                              and diametro_descrizione(r["descrizione"]) in diametri), None)
                if stesso:
                    esito, ordine, quando = "riuscito", stesso["id"], stesso["data_ora"]
                elif altra:
                    esito, ordine, quando = "riuscito_altra_ruota", altra["id"], altra["data_ora"]
                elif oggi > fine.date():
                    esito = "non_riuscito"
                else:
                    esito = "in_corso"
            con.execute("UPDATE preventivi SET esito=?, esito_ordine=?, esito_data=? WHERE id=?",
                        (esito, ordine, quando, p["id"]))
            conta[esito] = conta.get(esito, 0) + 1
    print("esiti:", ", ".join(f"{k} {v}" for k, v in sorted(conta.items())) or "nessun preventivo")
    return conta


def riepilogo(con):
    righe = con.execute("""SELECT substr(data_ora,1,7) mese, esito, count(*) n FROM preventivi
                           GROUP BY mese, esito ORDER BY mese""").fetchall()
    if not righe:
        print("nessun preventivo nel database")
        return
    mesi = {}
    for r in righe:
        mesi.setdefault(r["mese"], {})[r["esito"]] = r["n"]
    print(f"{'mese':8} {'tot':>4} {'riusc':>6} {'altra':>6} {'non':>5} {'corso':>6} {'abbin':>6} {'tasso':>6}")
    for mese, e in mesi.items():
        chiusi = e.get("riuscito", 0) + e.get("riuscito_altra_ruota", 0) + e.get("non_riuscito", 0)
        tasso = f"{100 * (e.get('riuscito', 0) + e.get('riuscito_altra_ruota', 0)) / chiusi:.0f}%" if chiusi else "-"
        print(f"{mese:8} {sum(e.values()):>4} {e.get('riuscito', 0):>6} {e.get('riuscito_altra_ruota', 0):>6} "
              f"{e.get('non_riuscito', 0):>5} {e.get('in_corso', 0):>6} {e.get('da_abbinare', 0):>6} {tasso:>6}")


def main(argv):
    comando = argv[1] if len(argv) > 1 else ""
    if comando == "clienti":
        esporta_clienti()
        return
    if comando not in ("importa", "esiti", "riepilogo", "notte"):
        raise SystemExit(__doc__)
    con = apri()
    if comando in ("importa", "notte"):
        importa(con)
    if comando in ("esiti", "notte"):
        calcola_esiti(con)
    if comando == "riepilogo":
        riepilogo(con)


if __name__ == "__main__":
    main(sys.argv)
