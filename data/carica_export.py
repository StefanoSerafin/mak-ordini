#!/usr/bin/env python3
"""Carica in data/ordini.db i due export del gestionale scaricati dal B2B
(Mak/mak-export-b2b/dati/ultimo-OR.xlsx e ultimo-CLI.xlsx).

    python3 data/carica_export.py            # carica tutti e due e stampa il report
    python3 data/carica_export.py --report   # solo il confronto, senza scrivere

Regole (piano plans/2026-10-28-export-gestionale-nel-database-ordini.md):
- gestionale_righe e anagrafica_b2b si riscrivono per intero: l'export e' una fotografia completa;
- ordini presenti in tutti e due: fonte='entrambi', merce_gestionale = somma Imp.Ord.;
- ordini solo nell'export (inseriti dalla sede, email mancanti): entrano in ordini e righe, fonte='gestionale';
- ordini del DB assenti dall'export e piu' vecchi del suo ultimo giorno: annullato=1 (gli omaggi no:
  il gestionale non li riporta e in pagina valgono gia' 0);
- dall'anagrafica si leggono SOLO le colonne di COLONNE_CLI: mai utente/password B2B, telefoni,
  cellulari, email, indirizzi.
"""
import argparse
import os
import re
import sys
import warnings

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
import carica_db  # noqa: E402

EXPORT_DIR = os.path.normpath(os.path.join(QUI, "..", "..", "mak-export-b2b", "dati"))
FILE_OR = os.path.join(EXPORT_DIR, "ultimo-OR.xlsx")
FILE_CLI = os.path.join(EXPORT_DIR, "ultimo-CLI.xlsx")

# intestazione dell'export -> colonna di gestionale_righe
COLONNE_OR = {
    "St.Ord.": "st_ord", "Dt.Ord.": "dt_ord", "Canale": "canale", "Ordine": "ordine",
    "Rif.Cliente": "rif_cliente", "Cod.Cliente": "cod_cliente", "Rag.Soc.Cliente": "ragione_sociale",
    "Località": "localita", "Pr": "provincia", "Cod.Articolo": "cod_articolo",
    "Descr.Articolo": "descrizione", "Diam.": "diametro", "Qtà.Ord.": "qta_ord", "Dt.Cons.": "dt_cons",
    "Imp.Ord.": "imp_ord", "Qtà.Spe.": "qta_spe", "Imp.Spe.": "imp_spe", "Qtà.Res.": "qta_res",
    "Imp.Res.": "imp_res", "St.Riga": "st_riga", "Auto-Marca": "auto_marca",
    "Auto-Modello": "auto_modello", "Mag": "mag",
}
# lista bianca dell'anagrafica: intestazione -> colonna di anagrafica_b2b (prima occorrenza)
COLONNE_CLI = {
    "Codice": "codice", "Rag.Sociale": "ragione_sociale", "Tipo": "tipo", "NetWork": "network",
    "Network 2": "network2", "Località": "localita", "Pr": "provincia", "Listino": "listino",
    "Campagna": "campagna", "Pagamento": "pagamento", "B2B": "b2b", "B2B Ult.Acc.": "b2b_ultimo",
    "Fatt.Prec.": "fatt_prec", "FATT.CORR.": "fatt_corr", "Ult.Acq.TPMS Univ.": "ult_acq_tpms",
    "Tool TPMS": "tool_tpms", "Des.Tool ORANGE": "tool_orange", "Des.Tool AUTEL": "tool_autel",
    "Des.Tool ATEQ": "tool_ateq", "OBD II": "obd", "Whatsapp": "whatsapp", "Marca": "marca",
    "Priorità": "priorita", "P.Iva": "piva", "CF": "cod_fiscale",
}
INSERITO_DA = {"B2BCLI": "cliente", "B2BAGE": "agente"}   # tutto il resto: sede o altro


def leggi(path, mappa, titolo):
    """Righe dell'export come dict con le sole colonne di `mappa`. Riga 1 = titolo, riga 2 = intestazione."""
    import openpyxl
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
        righe = ws.iter_rows(values_only=True)
        testa = next(righe)
        if not str(testa[0] or "").startswith(titolo):
            raise ValueError(f"{os.path.basename(path)}: atteso «{titolo}», trovato «{testa[0]}»")
        intest = [str(x).strip() if x is not None else "" for x in next(righe)]
        idx = {}
        for i, h in enumerate(intest):
            if h in mappa and mappa[h] not in idx:      # prima occorrenza (Località/Pr compaiono due volte)
                idx[mappa[h]] = i
        mancanti = set(mappa.values()) - set(idx)
        if mancanti:
            raise ValueError(f"{os.path.basename(path)}: colonne mancanti {sorted(mancanti)}")
        out = []
        for r in righe:
            d = {}
            for k, i in idx.items():
                v = r[i] if i < len(r) else None
                d[k] = v.strip() if isinstance(v, str) else v
            out.append(d)
        return out


def id_ordine(s):
    """'OR.I803600' -> 'I_803600' (come il Riferimento Interno dei PDF)."""
    cifre = re.sub(r"\D", "", s or "")
    return f"I_{cifre}" if cifre else None


def data_gestionale(v):
    """20260522 / '20260522' -> '2026-05-22'; 0 o vuoto -> None."""
    s = re.sub(r"\D", "", str(v or ""))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s != "00000000" else None


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def carica_ordini(con, path=FILE_OR, cfg=None):
    cfg = cfg or carica_db.carica_regole()
    righe = leggi(path, COLONNE_OR, "Dettaglio Righe Ordini")
    per_ordine = {}
    for r in righe:
        oid = id_ordine(r["ordine"])
        if not oid:
            continue
        r["ordine_id"] = oid
        r["cod_cliente"] = str(r["cod_cliente"] or "").zfill(6)
        r["categoria"] = carica_db.categoria(r["cod_articolo"], r["descrizione"], cfg)
        per_ordine.setdefault(oid, []).append(r)
    if not per_ordine:
        raise ValueError("export ordini vuoto")
    ultimo_giorno = max(rr[0]["dt_ord"] for rr in per_ordine.values())
    nel_db = {x["id"]: x for x in con.execute("SELECT id, merce_righe, fonte FROM ordini")}
    stat = {"ordini_export": len(per_ordine), "righe_export": len(righe), "abbinati": 0, "inseriti": 0,
            "importo_diverso": 0, "ultimo_giorno": ultimo_giorno}
    cols = ["ordine_id", "st_ord", "dt_ord", "canale", "rif_cliente", "cod_cliente", "cod_articolo",
            "descrizione", "diametro", "qta_ord", "dt_cons", "imp_ord", "qta_spe", "imp_spe", "qta_res",
            "imp_res", "st_riga", "auto_marca", "auto_modello", "mag", "categoria"]
    toccati = set()
    with con:
        con.execute("DELETE FROM gestionale_righe")
        con.executemany(f"INSERT INTO gestionale_righe ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [tuple(r[c] for c in cols) for r in righe if r.get("ordine_id")])
        for oid, rr in per_ordine.items():
            t = rr[0]
            merce = round(sum(num(r["imp_ord"]) for r in rr), 2)
            toccati.add(t["cod_cliente"])
            if oid in nel_db:
                stat["abbinati"] += 1
                if abs(merce - (nel_db[oid]["merce_righe"] or 0)) > 0.5:
                    stat["importo_diverso"] += 1
                fonte = "gestionale" if nel_db[oid]["fonte"] == "gestionale" else "entrambi"
                con.execute("UPDATE ordini SET merce_gestionale=?, stato_gestionale=?, canale=?, fonte=?, annullato=0"
                            " WHERE id=?", (merce, t["st_ord"], t["canale"], fonte, oid))
                if fonte == "gestionale":   # gia' inserito da un giro precedente: righe allineate all'export
                    con.execute("DELETE FROM righe WHERE ordine_id=?", (oid,))
                    _righe_da_export(con, oid, rr)
                    con.execute("UPDATE ordini SET merce_righe=? WHERE id=?", (merce, oid))
                continue
            stat["inseriti"] += 1
            if not con.execute("SELECT 1 FROM clienti WHERE codice=?", (t["cod_cliente"],)).fetchone():
                con.execute("INSERT INTO clienti (codice, ragione_sociale, citta, provincia) VALUES (?,?,?,?)",
                            (t["cod_cliente"], t["ragione_sociale"], t["localita"], t["provincia"]))
            con.execute(
                "INSERT INTO ordini (id, codice_cliente, data_ora, inserito_da, utente_raw, omaggio, merce_righe,"
                " fonte, merce_gestionale, stato_gestionale, canale, annullato) VALUES (?,?,?,?,?,0,?,?,?,?,?,0)",
                (oid, t["cod_cliente"], f"{t['dt_ord']} 00:00:00", INSERITO_DA.get(t["canale"], "altro"),
                 t["canale"], merce, "gestionale", merce, t["st_ord"], t["canale"]))
            _righe_da_export(con, oid, rr)
        # annullati: nel DB ma non nell'export, di un giorno precedente all'ultimo dell'export
        con.execute("UPDATE ordini SET annullato=0 WHERE id IN (SELECT DISTINCT ordine_id FROM gestionale_righe)")
        cur = con.execute("UPDATE ordini SET annullato=1 WHERE omaggio=0 AND substr(data_ora,1,10) < ?"
                          " AND id NOT IN (SELECT DISTINCT ordine_id FROM gestionale_righe)", (ultimo_giorno,))
        stat["annullati"] = cur.rowcount
        for x in con.execute("SELECT DISTINCT codice_cliente FROM ordini WHERE annullato=1"):
            toccati.add(x[0])
        for cod in toccati:
            con.execute("UPDATE clienti SET primo_ordine=(SELECT MIN(data_ora) FROM ordini WHERE codice_cliente=?"
                        " AND annullato=0), ultimo_ordine=(SELECT MAX(data_ora) FROM ordini WHERE codice_cliente=?"
                        " AND annullato=0) WHERE codice=?", (cod, cod, cod))
    return stat


def _righe_da_export(con, oid, rr):
    for n, r in enumerate(rr, 1):
        q, imp = num(r["qta_ord"]), num(r["imp_ord"])
        vettura = " ".join(x for x in (r["auto_marca"], r["auto_modello"]) if x)
        con.execute("INSERT INTO righe (ordine_id, n_riga, cod_articolo, descrizione, applicazione, qta, prezzo,"
                    " importo, categoria) VALUES (?,?,?,?,?,?,?,?,?)",
                    (oid, n, r["cod_articolo"], r["descrizione"], vettura or None, q,
                     round(imp / q, 2) if q else 0, imp, r["categoria"]))


def carica_anagrafica(con, path=FILE_CLI):
    righe = leggi(path, COLONNE_CLI, "Archivio Clienti")
    cols = list(COLONNE_CLI.values())
    dati = []
    for r in righe:
        if not r["codice"]:
            continue
        r["codice"] = str(r["codice"]).zfill(6)
        r["ragione_sociale"] = re.sub(r"\*+$", "", r["ragione_sociale"] or "").strip()
        r["b2b_ultimo"] = data_gestionale(r["b2b_ultimo"])
        r["ult_acq_tpms"] = data_gestionale(r["ult_acq_tpms"])
        r["fatt_prec"], r["fatt_corr"] = num(r["fatt_prec"]), num(r["fatt_corr"])
        r["b2b"] = int(num(r["b2b"]))
        for k in cols:
            if r[k] == "":
                r[k] = None
        dati.append(tuple(r[c] for c in cols))
    with con:
        con.execute("DELETE FROM anagrafica_b2b")
        con.executemany(f"INSERT OR REPLACE INTO anagrafica_b2b ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        dati)
        # network, tipo, P.IVA e "in anagrafica" dal gestionale (prima: corpo delle notifiche e file madre)
        con.execute("UPDATE clienti SET in_anagrafica=0")
        con.execute("""UPDATE clienti SET in_anagrafica=1,
                         network=(SELECT a.network FROM anagrafica_b2b a WHERE a.codice=clienti.codice),
                         tipo=(SELECT a.tipo FROM anagrafica_b2b a WHERE a.codice=clienti.codice),
                         piva=COALESCE((SELECT a.piva FROM anagrafica_b2b a WHERE a.codice=clienti.codice), piva)
                       WHERE codice IN (SELECT codice FROM anagrafica_b2b)""")
    return {"clienti_anagrafica": len(dati)}


def carica(con=None, verbose=True):
    """Carica gli export presenti; salta in silenzio quelli che mancano. Ritorna le statistiche."""
    con = con or carica_db.apri()
    stat = {}
    if os.path.exists(FILE_OR):
        stat.update(carica_ordini(con))
    if os.path.exists(FILE_CLI):
        stat.update(carica_anagrafica(con))
    if verbose and stat:
        stampa(con, stat)
    return stat


def stampa(con, stat):
    if "ordini_export" in stat:
        print(f"Export ordini: {stat['ordini_export']} ordini ({stat['righe_export']} righe) fino al "
              f"{stat['ultimo_giorno']} | abbinati {stat['abbinati']} | inseriti dal gestionale {stat['inseriti']} | "
              f"importo diverso {stat['importo_diverso']} | annullati {stat['annullati']}")
    if "clienti_anagrafica" in stat:
        print(f"Anagrafica gestionale: {stat['clienti_anagrafica']} clienti")
    for x in con.execute("SELECT substr(data_ora,1,4) a, COUNT(*) n,"
                         " SUM(CASE WHEN omaggio=0 THEN COALESCE(merce_gestionale, merce_righe) ELSE 0 END) s,"
                         " SUM(CASE WHEN omaggio=0 THEN merce_righe ELSE 0 END) m"
                         " FROM ordini WHERE annullato=0 GROUP BY 1 ORDER BY 1"):
        print(f"  {x['a']}: {x['n']} ordini, merce {x['s']:.2f} (importi delle email: {x['m']:.2f})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="solo il riepilogo, senza caricare")
    a = ap.parse_args()
    con = carica_db.apri()
    if a.report:
        stampa(con, {})
        return 0
    if not (os.path.exists(FILE_OR) or os.path.exists(FILE_CLI)):
        sys.exit(f"Nessun export in {EXPORT_DIR}: lancia prima mak-export-b2b/scarica.py")
    carica(con)
    return 0


if __name__ == "__main__":
    sys.exit(main())
