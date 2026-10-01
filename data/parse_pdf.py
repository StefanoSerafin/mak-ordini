#!/usr/bin/env python3
"""Da PDF "ORDINE_I_..." del B2B MAK a dizionario (testata, righe, totali).

    python3 data/parse_pdf.py data/pdf/I_797262.pdf     # stampa il risultato

parse_testo() lavora sul testo gia' estratto: e' quello che usano i test.
"""
import datetime
import json
import re
import sys

RE_NUM_IT = r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}"
# coda di una riga articolo: Qta Prezzo [Sconti] Importo
RE_RIGA = re.compile(
    rf"^(?P<cod>\S+)\s+(?:(?P<desc>.*?)\s+)?(?P<qta>{RE_NUM_IT})\s+(?P<prezzo>{RE_NUM_IT})"
    rf"(?:\s+(?P<sconto>\d+(?:[.,]\d+)?(?:\s*\+\s*\d+(?:[.,]\d+)?)*))?\s+(?P<importo>{RE_NUM_IT})$"
)
RE_DATA = re.compile(r"Data - Ora:\s*(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2}):(\d{2})")
RE_PAGINA = re.compile(r"^\d+/\d+$")
RE_FLAG = re.compile(r"^\(([A-Z])\)\s+")
RE_CAP = re.compile(r"^(\d{5})\s+(.+?)\s+([A-Z]{2})\s+([A-Z]{2})$")
RE_KIT = re.compile(r"^Kit Completo", re.I)

ETICHETTE_DX = ["Termini di Pagamento", "Modalità Consegna", "Spedizione", "Vettore"]
TOTALI = {
    "Importo Totale": "totale", "Importo PFU": "pfu", "Importo Merce": "merce",
    "Costi di Spedizione": "spedizione", "Importo Imponibile": "imponibile", "Imposta (Iva)": "iva",
    "Costo Contrass.": "contrassegno",
}
RE_COSTO_IGNOTO = re.compile(r"^(?P<nome>\D.*?)\s+(?P<val>-?\d+\.\d{1,2})$")
RE_COUPON = re.compile(r"\s*\[Cod\. Coupon:\s*([^\]]*)\]")


# Alcuni clienti hanno il portale in inglese: stesso contenuto, etichette diverse.
# L'ordine conta ("Customer Code" prima di "Customer", "Total amount of goods" prima di "Total Amount").
EN_IT = [
    (re.compile(r"^Date - Time:", re.M), "Data - Ora:"),
    (re.compile(r"^Page (\d+/\d+)$", re.M), r"Pagina\n\1"),
    (re.compile(r"^User:", re.M), "Utente:"),
    (re.compile(r"^Internal Reference\s+(I_\d+)", re.M), r"Riferimento Interno\n\1"),
    (re.compile(r"^Customer Code\b", re.M), "Codice Cliente"),
    (re.compile(r"^Customer\b", re.M), "Cliente"),
    (re.compile(r"\bSales Rep\.", re.M), "Agente"),
    (re.compile(r"^VAT Code\b", re.M), "Partita Iva"),
    (re.compile(r"\bPayment Terms\b"), "Termini di Pagamento"),
    (re.compile(r"^Fiscal Code\b", re.M), "Codice Fiscale"),
    (re.compile(r"\bDelivery Terms\b"), "Modalità Consegna"),
    (re.compile(r"^Shipment Method\b", re.M), "Tipo Consegna"),
    (re.compile(r"\bCarrier\b"), "Vettore"),
    (re.compile(r"^Item Code\b.*$", re.M), "Cod.Articolo Descrizione Qtà Prezzo Sconti Importo"),
    (re.compile(r"^Total amount of goods\b", re.M), "Importo Merce"),
    (re.compile(r"^Total Amount\b", re.M), "Importo Totale"),
    (re.compile(r"^Shipment cost\b", re.M), "Costi di Spedizione"),
    (re.compile(r"^Taxable Amount\b", re.M), "Importo Imponibile"),
    (re.compile(r"^VAT \(If applicable\)", re.M), "Imposta (Iva)"),
]


# Variante italiana compatta (vista su un ordine di gennaio 2026).
IT_VARIANTE = [
    (re.compile(r"^Pag\. (\d+/\d+)$", re.M), r"Pagina\n\1"),
    (re.compile(r"^Rif\.Interno:\s*(I_\d+)", re.M), r"Riferimento Interno\n\1"),
    (re.compile(r"^(Partita Iva(?:(?!Termini di Pagamento).)*?) Pagamento ", re.M), r"\1 Termini di Pagamento "),
    (re.compile(r"^Imponibile (?=-?\d)", re.M), "Importo Imponibile "),
]


class OrdineNonValido(Exception):
    pass


def num_it(s):
    return float(s.replace(".", "").replace(",", "."))


def _dopo(riga, etichetta):
    i = riga.find(etichetta)
    return riga[i + len(etichetta):].strip() if i >= 0 else None


def _tra(riga, sx, dx_possibili):
    """Testo dopo l'etichetta sx, fino alla prima etichetta di destra presente."""
    v = _dopo(riga, sx)
    if v is None:
        return None
    for dx in dx_possibili:
        j = v.find(dx)
        if j >= 0:
            v = v[:j]
    return v.strip()


def parse_testo(testo):
    for rx, it in IT_VARIANTE:
        testo = rx.sub(it, testo)
    if "Internal Reference" in testo:
        for rx, it in EN_IT:
            testo = rx.sub(it, testo)
    righe_txt = [r.strip() for r in testo.splitlines() if r.strip()]
    o = {
        "id": None, "data_ora": None, "utente_raw": None, "inserito_da": None,
        "codice_cliente": None, "ragione_sociale": None, "cod_network": None, "flag_cliente": None,
        "indirizzo": None, "cap": None, "citta": None, "provincia": None,
        "piva": None, "cod_fiscale": None, "termini_pagamento": None, "vettore": None,
        "kit_completo": 0, "righe": [],
        "totale": None, "pfu": None, "merce": None, "spedizione": None, "imponibile": None, "iva": None,
        "contrassegno": None, "altri_costi": 0.0, "altri_costi_voci": [],
    }

    m = RE_DATA.search(testo)
    if m:
        g, me, a, h, mi, s = map(int, m.groups())
        o["data_ora"] = datetime.datetime(a, me, g, h, mi, s).isoformat(sep=" ")

    in_righe = False
    kit_veicolo_atteso = False
    veicolo_kit = None
    note = []
    orfano = None       # numero rimasto da solo su una riga nella zona totali
    pendente = None     # ultima riga di solo testo: (riga a cui e' stata attaccata, testo, applicazione di prima)
    for i, r in enumerate(righe_txt):
        if r.startswith("Cod.Articolo"):
            in_righe = True     # su PDF multipagina l'intestazione si ripete: si resta in_righe
            continue
        if not in_righe:
            if r.startswith("Utente:"):
                o["utente_raw"] = r.split(":", 1)[1].strip()
            elif r == "Riferimento Interno" and i + 1 < len(righe_txt):
                # "I_755610" oppure "I_755610 Omaggio": dopo l'ID puo' esserci un riferimento libero
                mm = re.match(r"^(I_\d+)\b\s*(.*)$", righe_txt[i + 1].strip())
                if mm:
                    o["id"] = mm.group(1)
                    if mm.group(2):
                        note.append(mm.group(2))
            elif r.startswith("Note Carrello"):
                if r[len("Note Carrello"):].strip():
                    note.append(r[len("Note Carrello"):].strip())
            elif r.startswith("Cliente ") and o["ragione_sociale"] is None:
                corpo = r[len("Cliente "):]
                mm = re.search(r"\s(?:Cod\. Cli\. MAK\s+)?(\d{6})\s+\d{2}$", corpo)
                if mm:
                    o["ragione_sociale"] = corpo[:mm.start()].strip()
                else:
                    o["ragione_sociale"] = corpo.strip()
                # riga successiva: [(F)] indirizzo [Cod. Cli. Net. xxx] Agente SS
                if i + 1 < len(righe_txt):
                    ind = righe_txt[i + 1]
                    mf = RE_FLAG.match(ind)
                    if mf:
                        o["flag_cliente"] = mf.group(1)
                        ind = ind[mf.end():]
                    ind = re.sub(r"\s*Agente\s+\S+$", "", ind)
                    mn = re.search(r"\s*Cod\. Cli\. Net\.\s*(\S*)$", ind)
                    if mn:
                        o["cod_network"] = mn.group(1) or None
                        ind = ind[:mn.start()]
                    o["indirizzo"] = ind.strip() or None
                if i + 2 < len(righe_txt):
                    mc = RE_CAP.match(righe_txt[i + 2])
                    if mc:
                        o["cap"], o["citta"], o["provincia"] = mc.group(1), mc.group(2), mc.group(3)
            elif r.startswith("Partita Iva"):
                o["piva"] = _tra(r, "Partita Iva", ETICHETTE_DX) or None
                o["termini_pagamento"] = _dopo(r, "Termini di Pagamento") or None
            elif r.startswith("Codice Fiscale"):
                o["cod_fiscale"] = _tra(r, "Codice Fiscale", ETICHETTE_DX) or None
            elif r.startswith("Codice Cliente"):
                mm = re.match(r"Codice Cliente\s+(\d{6})\b", r)
                if mm:
                    o["codice_cliente"] = mm.group(1)
            elif r.startswith("Tipo Consegna"):
                o["vettore"] = _dopo(r, "Vettore") or None
            continue

        # --- zona righe / totali ---
        tot = next((k for k in TOTALI if r.startswith(k)), None)
        if tot:
            v = r[len(tot):].strip()
            if not v and orfano is not None:
                v, orfano = orfano, None    # a cavallo di un cambio pagina il valore finisce sulla riga prima dell'etichetta
            try:
                o[TOTALI[tot]] = float(v)
            except ValueError:
                pass
            continue
        if o["totale"] is not None and re.match(r"^-?\d+(\.\d+)?$", r):
            orfano = r
            continue
        if r.startswith("ORDINE ") or r.startswith("Data - Ora:") or r == "Pagina" or RE_PAGINA.match(r) \
                or r.startswith("Utente:") or r == "Riferimento Interno" or r == o["id"]:
            continue
        if RE_KIT.match(r):
            o["kit_completo"] = 1
            kit_veicolo_atteso = True
            continue
        mr = RE_RIGA.match(r)
        mc = RE_COSTO_IGNOTO.match(r) if not mr and o["totale"] is not None else None
        if mc:
            # voce di costo non prevista nella zona totali: si tiene per la quadratura
            o["altri_costi"] = round(o["altri_costi"] + float(mc.group("val")), 2)
            o["altri_costi_voci"].append(mc.group("nome"))
            continue
        if mr:
            kit_veicolo_atteso = False
            desc = (mr.group("desc") or "").strip()
            if not desc and pendente is not None:
                # la descrizione era andata a capo PRIMA del codice: la si toglie
                # dall'applicazione della riga precedente, dove era finita
                riga_p, testo_p, prima_p = pendente
                if riga_p is not None:
                    riga_p["applicazione"] = prima_p
                elif veicolo_kit == testo_p:
                    veicolo_kit = None
                desc = testo_p
            pendente = None
            mcp = RE_COUPON.search(desc)
            o["righe"].append({
                "cod_articolo": mr.group("cod"),
                "descrizione": RE_COUPON.sub("", desc).strip(),
                "coupon": mcp.group(1).strip() if mcp else None,
                "applicazione": veicolo_kit,
                "qta": num_it(mr.group("qta")),
                "prezzo": num_it(mr.group("prezzo")),
                "sconto": mr.group("sconto"),
                "importo": num_it(mr.group("importo")),
            })
        elif kit_veicolo_atteso:
            veicolo_kit = r
            kit_veicolo_atteso = False
            pendente = (None, r, None)
        elif o["righe"]:
            # riga senza coda numerica = applicazione veicolo della riga precedente
            prec = o["righe"][-1]
            if not prec["descrizione"]:
                # descrizione andata a capo DOPO codice e numeri
                mcp = RE_COUPON.search(r)
                prec["descrizione"] = RE_COUPON.sub("", r).strip()
                if mcp:
                    prec["coupon"] = mcp.group(1).strip()
                continue
            pendente = (prec, r, prec["applicazione"])
            if veicolo_kit is None or prec["applicazione"] is None:
                prec["applicazione"] = r if not prec["applicazione"] else prec["applicazione"] + " " + r
        else:
            pendente = (None, r, None)

    o["nota"] = " | ".join(note) or None
    u = o["utente_raw"] or ""
    if u == "s.serafin":
        o["inserito_da"] = "agente"
    elif re.match(r"^cl\d+\.", u):
        o["inserito_da"] = "cliente"
    else:
        o["inserito_da"] = "altro"

    if not o["id"] or not re.match(r"^I_\d+$", o["id"]):
        raise OrdineNonValido("Riferimento Interno assente")
    if not o["codice_cliente"]:
        raise OrdineNonValido("Codice Cliente assente")
    if not o["righe"]:
        raise OrdineNonValido("nessuna riga articolo riconosciuta")
    return o


def testo_pdf(percorso):
    import pdfplumber
    with pdfplumber.open(percorso) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages), len(pdf.pages)


def parse_pdf(percorso):
    testo, pagine = testo_pdf(percorso)
    o = parse_testo(testo)
    o["pagine"] = pagine
    return o


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps(parse_pdf(p), ensure_ascii=False, indent=1))
