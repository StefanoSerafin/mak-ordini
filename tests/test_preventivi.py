"""Test dei preventivi nel database (data/preventivi.py) su dati INVENTATI: questo repo è pubblico.

    python3 -m unittest discover -s tests
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
import preventivi as P  # noqa: E402

CLIENTI = [{"codice": "000111", "nome": "GOMME PROVA SRL", "listino": "SD", "network": ""},
           {"codice": "000222", "nome": "OFFICINA ESEMPIO SNC", "listino": "SQ", "network": ""},
           {"codice": "000333", "nome": "SRL", "listino": "", "network": ""}]   # nome che si svuota


def preventivo(pid, quando, codice="000111", nome="GOMME PROVA SRL", articoli=None):
    return {"id": pid, "data_ora": quando, "cliente_codice": codice, "cliente_nome": nome,
            "vettura": {"marca": "FIAT", "modello": "PROVA", "testo": "FIAT PROVA"}, "listino": "SD",
            "articoli": articoli or [
                {"codiceArticolo": "F6560AAAA32XX", "code": "F6560AAAA32XX", "tipo": "lega", "modello": "PROVA",
                 "diametro": "16", "netto": 100.0},
                {"codiceArticolo": "F6560CCMB32ZZ", "code": "R1-9999", "tipo": "acciaio", "modello": "ACCIAIO R1-9999",
                 "diametro": "16", "netto": 50.0}],
            "tpms": None}


class TestPreventivi(unittest.TestCase):
    def setUp(self):
        self.con = P.apri(":memory:")
        with self.con:
            for c in ("000111", "000222"):
                self.con.execute("INSERT INTO clienti (codice, ragione_sociale) VALUES (?, ?)", (c, "X"))

    def ordine(self, oid, quando, cod, descr="6,5J16 PROVA ET32", cat="Ruote lega", cliente="000111"):
        with self.con:
            self.con.execute("INSERT INTO ordini (id, codice_cliente, data_ora) VALUES (?,?,?)", (oid, cliente, quando))
            self.con.execute("INSERT INTO righe (ordine_id, cod_articolo, descrizione, categoria) VALUES (?,?,?,?)",
                             (oid, cod, descr, cat))

    def esito(self, pid):
        return self.con.execute("SELECT esito, esito_ordine FROM preventivi WHERE id=?", (pid,)).fetchone()

    def carica(self, prev, abbinamenti=None):
        P.carica(self.con, prev, clienti=CLIENTI, abbinamenti=abbinamenti or {})

    def test_stesso_codice_entro_30_giorni(self):
        self.carica([preventivo("20261001-100000-aaaa", "2026-10-01T10:00:00")])
        self.ordine("I_1", "2026-10-20 09:00:00", "F6560AAAA32XX")
        P.calcola_esiti(self.con, oggi=dt.date(2026, 10, 25))
        self.assertEqual(tuple(self.esito("20261001-100000-aaaa")), ("riuscito", "I_1"))

    def test_acciaio_col_codice_f(self):
        self.carica([preventivo("20261001-100000-aaaa", "2026-10-01T10:00:00")])
        self.ordine("I_1", "2026-10-05 09:00:00", "F6560CCMB32ZZ", "6,5J16 AC 9999 E32", "Ruote acciaio")
        P.calcola_esiti(self.con, oggi=dt.date(2026, 10, 25))
        self.assertEqual(self.esito("20261001-100000-aaaa")["esito"], "riuscito")

    def test_dopo_30_giorni_non_conta(self):
        self.carica([preventivo("20260901-100000-aaaa", "2026-09-01T10:00:00")])
        self.ordine("I_1", "2026-10-02 09:00:00", "F6560AAAA32XX")   # 31° giorno
        P.calcola_esiti(self.con, oggi=dt.date(2026, 10, 25))
        self.assertEqual(self.esito("20260901-100000-aaaa")["esito"], "non_riuscito")

    def test_altra_ruota_stesso_diametro(self):
        self.carica([preventivo("20261001-100000-aaaa", "2026-10-01T10:00:00")])
        self.ordine("I_1", "2026-10-03 09:00:00", "F6560BBBB40YY", "6,5J16 ALTRA ET40")
        self.ordine("I_2", "2026-10-04 09:00:00", "F7070CCCC40YY", "7J17 ALTRA ET40")  # diametro diverso: non conta
        P.calcola_esiti(self.con, oggi=dt.date(2026, 10, 25))
        self.assertEqual(tuple(self.esito("20261001-100000-aaaa")), ("riuscito_altra_ruota", "I_1"))

    def test_ordine_di_un_altro_cliente_non_conta(self):
        self.carica([preventivo("20261001-100000-aaaa", "2026-10-01T10:00:00")])
        self.ordine("I_1", "2026-10-03 09:00:00", "F6560AAAA32XX", cliente="000222")
        P.calcola_esiti(self.con, oggi=dt.date(2026, 10, 11))
        self.assertEqual(self.esito("20261001-100000-aaaa")["esito"], "in_corso")
        P.calcola_esiti(self.con, oggi=dt.date(2026, 11, 1))
        self.assertEqual(self.esito("20261001-100000-aaaa")["esito"], "non_riuscito")

    def test_ordine_prima_del_preventivo_non_conta(self):
        self.carica([preventivo("20261010-100000-aaaa", "2026-10-10T10:00:00")])
        self.ordine("I_1", "2026-10-09 09:00:00", "F6560AAAA32XX")
        P.calcola_esiti(self.con, oggi=dt.date(2026, 10, 12))
        self.assertEqual(self.esito("20261010-100000-aaaa")["esito"], "in_corso")

    def test_abbinamenti(self):
        self.carica([
            preventivo("20261001-100000-aaaa", "2026-10-01T10:00:00", codice="", nome="Officina Esempio s.n.c."),
            preventivo("20261001-100001-bbbb", "2026-10-01T10:00:01", codice="", nome=""),
            preventivo("20261001-100002-cccc", "2026-10-01T10:00:02", codice="", nome="Sconosciuto"),
            preventivo("20261001-100003-dddd", "2026-10-01T10:00:03", codice="", nome="Sconosciuto 2"),
        ], abbinamenti={"20261001-100003-dddd": "111"})
        righe = {r["id"]: (r["cliente_codice"], r["abbinato"]) for r in self.con.execute("SELECT * FROM preventivi")}
        self.assertEqual(righe["20261001-100000-aaaa"], ("000222", "nome"))
        self.assertEqual(righe["20261001-100001-bbbb"], ("", ""))           # nome vuoto: mai abbinato
        self.assertEqual(righe["20261001-100002-cccc"], ("", ""))
        self.assertEqual(righe["20261001-100003-dddd"], ("000111", "manuale"))
        P.calcola_esiti(self.con, oggi=dt.date(2026, 10, 5))
        self.assertEqual(self.esito("20261001-100001-bbbb")["esito"], "da_abbinare")

    def test_ricarica_e_togli_mancanti(self):
        a = preventivo("20261001-100000-aaaa", "2026-10-01T10:00:00")
        b = preventivo("20261001-100001-bbbb", "2026-10-01T10:00:01")
        self.carica([a, b])
        self.carica([dict(a, listino="SJ")])   # rifatto: aggiorna, articoli non duplicati
        self.assertEqual(self.con.execute("SELECT count(*) FROM preventivi_articoli WHERE preventivo_id=?",
                                          (a["id"],)).fetchone()[0], 2)
        self.assertEqual(P.togli_mancanti(self.con, [a]), 1)
        self.assertEqual([r[0] for r in self.con.execute("SELECT id FROM preventivi")], [a["id"]])

    def test_diametro_dalla_descrizione(self):
        self.assertEqual(P.diametro_descrizione("6,5J16 APOLL/BGY ET32 4X108 65,1 BM IT"), "16")
        self.assertEqual(P.diametro_descrizione("7J17 EPICA/GD4X ET50"), "17")
        self.assertEqual(P.diametro_descrizione("RUOTINO 125/80"), "")


if __name__ == "__main__":
    unittest.main()
