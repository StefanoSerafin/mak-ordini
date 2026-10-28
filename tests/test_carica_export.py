"""Test del caricamento degli export del gestionale (data/carica_export.py) su dati INVENTATI:
questo repo è pubblico.

    /usr/bin/python3 -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
import carica_db  # noqa: E402
import carica_export as CE  # noqa: E402

try:
    import openpyxl
except ImportError:  # il Python di Homebrew non ce l'ha: usare /usr/bin/python3
    openpyxl = None

INTEST_OR = ["St.Ord.", "Dt.Ord.", "Canale", "PDF B2B", "Ordine", "Rif.Cliente", "Ag", "Cod.Cliente",
             "Rag.Soc.Cliente", "Destinatario", "Indirizzo", "Località", "Pr", "Cod.Articolo", "Descr.Articolo",
             "Diam.", "Qtà.Ord.", "Dt.Cons.", "Imp.Ord.", "Qtà.Spe.", "Imp.Spe.", "Qtà.Res.", "Imp.Res.",
             "St.Riga", "Auto-Marca", "Auto-Modello", "Mag"]
INTEST_CLI = ["Codice", "Ns.Cod.", "Tipo", "NetWork", "Network 2", "Rag.Sociale", "Indirizzo", "Cap", "Località",
              "Pr", "Zona", "Telefono (1)", "Cellulare", "Email", "Gruppo", "Listino", "Campagna", "Fino al",
              "Pagamento", "Capoarea", "Agente", "Agente 2", "SubAgente", "Destinatario", "Indirizzo", "Località",
              "Pr", "B2B", "B2B Id", "B2B Pwd", "B2B Ult.Acc.", "B2B Lampa", "Fatt.Prec.", "FP RUO Prz.SPC",
              "FATT.CORR.", "FC RUO PRZ.SPC.", "Ult.Acq.TPMS Univ.", "Tool TPMS", "Cod.Tool ORANGE",
              "Des.Tool ORANGE", "Cod.Tool AUTEL", "Des.Tool AUTEL", "Cod.Tool ATEQ", "Des.Tool ATEQ", "OBD II",
              "Cacciav.TPMS", "Whatsapp", "Marca", "Priorità", "Geoloc.", "P.Iva", "CF"]
SEGRETI = ["PWD-SEGRETA-123", "utente.segreto", "333 0000000", "segreto@example.com", "VIA SEGRETA 1"]


def riga_or(ordine, data, cliente, articolo, descr, qta, imp, canale="B2BCLI", res=0, marca="", modello=""):
    v = dict.fromkeys(INTEST_OR, "")
    v.update({"St.Ord.": "SA", "Dt.Ord.": data, "Canale": canale + "    ", "Ordine": f"OR.I{ordine}    ",
              "Cod.Cliente": cliente, "Rag.Soc.Cliente": "GOMME PROVA   ", "Località": "MILANO", "Pr": "MI",
              "Cod.Articolo": articolo, "Descr.Articolo": descr, "Qtà.Ord.": qta, "Imp.Ord.": imp,
              "Qtà.Res.": res, "Imp.Res.": 0, "Auto-Marca": marca, "Auto-Modello": modello})
    return [v[h] for h in INTEST_OR]


def riga_cli(codice):
    v = dict(zip(INTEST_CLI, [""] * len(INTEST_CLI)))
    vals = [""] * len(INTEST_CLI)
    v.update({"Codice": codice, "Tipo": "Gommisti", "NetWork": "DRIVER", "Rag.Sociale": "GOMME PROVA SRL******",
              "Listino": "SD SA+25", "Pagamento": "RICEVUTA 30 GG", "B2B": 1, "B2B Ult.Acc.": 20260115,
              "Fatt.Prec.": 1234.5, "FATT.CORR.": 99, "Ult.Acq.TPMS Univ.": "0", "Tool TPMS": "AUTEL",
              "Des.Tool AUTEL": "AUTEL PROGRAMMING TOOL TS508", "Whatsapp": "SI", "P.Iva": "01234567890"})
    for i, h in enumerate(INTEST_CLI):
        vals[i] = v[h] if v[h] != "" else vals[i]
    vals[INTEST_CLI.index("B2B Pwd")] = SEGRETI[0]
    vals[INTEST_CLI.index("B2B Id")] = SEGRETI[1]
    vals[INTEST_CLI.index("Cellulare")] = SEGRETI[2]
    vals[INTEST_CLI.index("Email")] = SEGRETI[3]
    vals[INTEST_CLI.index("Indirizzo")] = SEGRETI[4]
    return vals


def scrivi(path, titolo, intest, righe):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([titolo] + [None] * (len(intest) - 1))
    ws.append(intest)
    for r in righe:
        ws.append(r)
    wb.save(path)


@unittest.skipIf(openpyxl is None, "serve openpyxl (/usr/bin/python3)")
class TestCaricaExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_orig = carica_db.DB
        carica_db.DB = os.path.join(self.tmp.name, "prova.db")
        self.con = carica_db.apri()
        with self.con:
            self.con.execute("INSERT INTO clienti (codice, ragione_sociale) VALUES ('000111', 'GOMME PROVA')")
            for oid, quando, merce, om in (("I_100", "2026-01-10 09:00:00", 200.0, 0),   # in tutti e due, importo cambiato
                                           ("I_101", "2026-01-11 09:00:00", 50.0, 0),    # vecchio, assente: annullato
                                           ("I_102", "2026-01-20 18:00:00", 70.0, 0),    # ultimo giorno: non annullato
                                           ("I_103", "2026-01-05 09:00:00", 30.0, 1)):   # omaggio assente: resta omaggio
                self.con.execute("INSERT INTO ordini (id, codice_cliente, data_ora, omaggio, merce_righe) VALUES"
                                 " (?, '000111', ?, ?, ?)", (oid, quando, om, merce))
        self.f_or = os.path.join(self.tmp.name, "or.xlsx")
        self.f_cli = os.path.join(self.tmp.name, "cli.xlsx")
        scrivi(self.f_or, "Dettaglio Righe Ordini - 1", INTEST_OR, [
            riga_or("100", "2026-01-10", "000111", "F6560AAAA32XX", "6,5J16 PROVA ET32", 2, 100.0, res=2,
                    marca="FIAT", modello="PANDA"),
            riga_or("104", "2026-01-15", "000999", "NPK100", "RUOTINO NPK PROVA", 1, 80.0, canale="***"),
            riga_or("105", "2026-01-20", "000111", "NPK100", "RUOTINO NPK PROVA", 1, 40.0),
        ])
        scrivi(self.f_cli, "Archivio Clienti - 1", INTEST_CLI, [riga_cli("000111")])

    def tearDown(self):
        self.con.close()
        carica_db.DB = self.db_orig
        self.tmp.cleanup()

    def stato(self, oid):
        return self.con.execute("SELECT * FROM ordini WHERE id=?", (oid,)).fetchone()

    def test_id_ordine(self):
        self.assertEqual(CE.id_ordine("OR.I803600     "), "I_803600")
        self.assertEqual(CE.data_gestionale(20260522), "2026-05-22")
        self.assertIsNone(CE.data_gestionale(0))

    def test_ordini(self):
        s = CE.carica_ordini(self.con, self.f_or)
        self.assertEqual(s["abbinati"], 1)
        self.assertEqual(s["inseriti"], 2)
        o = self.stato("I_100")
        self.assertEqual((o["fonte"], o["merce_gestionale"], o["annullato"], o["modificato"], o["merce_righe"]),
                         ("entrambi", 100.0, 0, 1, 100.0))
        r100 = self.con.execute("SELECT importo, applicazione FROM righe WHERE ordine_id='I_100'").fetchall()
        self.assertEqual([tuple(x) for x in r100], [(100.0, "FIAT PANDA")])
        self.assertEqual(self.stato("I_101")["annullato"], 1)
        self.assertEqual(self.stato("I_102")["annullato"], 0)
        self.assertEqual((self.stato("I_103")["annullato"], self.stato("I_103")["omaggio"]), (0, 1))
        nuovo = self.stato("I_104")
        self.assertEqual((nuovo["fonte"], nuovo["inserito_da"], nuovo["merce_righe"]), ("gestionale", "altro", 80.0))
        r = self.con.execute("SELECT categoria, prezzo FROM righe WHERE ordine_id='I_104'").fetchone()
        self.assertTrue(r["categoria"])
        self.assertEqual(r["prezzo"], 80.0)
        self.assertIsNotNone(self.con.execute("SELECT 1 FROM clienti WHERE codice='000999'").fetchone())
        g = self.con.execute("SELECT qta_res, auto_marca FROM gestionale_righe WHERE ordine_id='I_100'").fetchone()
        self.assertEqual((g["qta_res"], g["auto_marca"]), (2, "FIAT"))
        # un secondo giro non duplica nulla
        CE.carica_ordini(self.con, self.f_or)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM righe WHERE ordine_id='I_104'").fetchone()[0], 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM gestionale_righe").fetchone()[0], 3)

    def test_subentri(self):
        orig = carica_db.subentri
        carica_db.subentri = lambda: {"000111": {"nuovo": "000777", "nota": "ex prova"}}
        try:
            CE.carica_ordini(self.con, self.f_or)
            self.assertEqual(carica_db.applica_subentri(self.con), 1)
            self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ordini WHERE codice_cliente='000111'").fetchone()[0], 0)
            self.assertGreater(self.con.execute("SELECT COUNT(*) FROM ordini WHERE codice_cliente='000777'").fetchone()[0], 0)
            self.assertIsNone(self.con.execute("SELECT 1 FROM clienti WHERE codice='000111'").fetchone())
            self.assertIsNotNone(self.con.execute("SELECT 1 FROM clienti WHERE codice='000777'").fetchone())
            self.assertEqual(carica_db.applica_subentri(self.con), 0)   # gia' applicato: niente da fare
        finally:
            carica_db.subentri = orig

    def test_anagrafica_senza_segreti(self):
        CE.carica_anagrafica(self.con, self.f_cli)
        a = self.con.execute("SELECT * FROM anagrafica_b2b WHERE codice='000111'").fetchone()
        self.assertEqual((a["ragione_sociale"], a["network"], a["b2b_ultimo"], a["ult_acq_tpms"]),
                         ("GOMME PROVA SRL", "DRIVER", "2026-01-15", None))
        c = self.con.execute("SELECT network, tipo, in_anagrafica, piva FROM clienti WHERE codice='000111'").fetchone()
        self.assertEqual(tuple(c), ("DRIVER", "Gommisti", 1, "01234567890"))
        tutto = "\n".join(self.con.iterdump())
        for s in SEGRETI:
            self.assertNotIn(s, tutto)


if __name__ == "__main__":
    unittest.main()
