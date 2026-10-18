"""Test delle regole di scelta del punto (data/coordinate.py), sui casi reali del 2026-10-18."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
from coordinate import _comune_coincide, _indirizzo_coincide, decidi, simile  # noqa: E402


def esito(geo, posti):
    return {"indirizzi": copy.deepcopy(geo), "posti": copy.deepcopy(posti)}


class TestConfronti(unittest.TestCase):
    def test_comune(self):
        self.assertTrue(_comune_coincide("BESANA BRIANZA", "", "Viale Kennedy, 99, 20842 Besana in Brianza MB"))
        self.assertTrue(_comune_coincide("SANTANGELO LODIGIAN", "", "Viale Trieste, 41, 26866 Sant'Angelo Lodigiano LO"))
        self.assertTrue(_comune_coincide("CASSANO DADDA", "", "Via Casotta, 24, 20062 Cassano d'Adda MI"))
        # stesso CAP, comune diverso
        self.assertFalse(_comune_coincide("MARUGGIO", "74020", "Via Cupelle, 38, 74020 Lizzano TA"))

    def test_indirizzo(self):
        self.assertTrue(_indirizzo_coincide("VIA G. DA SOVICO 129", "Via Giovanni da Sovico, 129, 20845 Sovico MB"))
        self.assertFalse(_indirizzo_coincide("VIA G. DA SOVICO 129", "Via Giovanni da Sovico, 12, 20845 Sovico MB"))

    def test_simile(self):
        self.assertTrue(simile("F.LLI CARFORA DI CARFORA M.E C. SNC", "Carforauto"))
        self.assertFalse(simile("SUPERTYRE SRL", "Super Car Service"))
        self.assertFalse(simile("CORSICO RICAMBI SRL", "Accessori e Ricambi Auto - NGM DREAM SRL"))


class TestDecidi(unittest.TestCase):
    def test_cap_vecchio(self):
        # 20090 Assago: Google Geocoding manda l'indirizzo a Cesano Boscone, l'officina e' ad Assago
        geo = {"ordine": {"lat": 45.4366, "lng": 9.1038, "tipo": "ROOFTOP", "ind": "Via Giuseppe Garibaldi, 7, 20090 Cesano Boscone MI"}}
        posti = [{"nome": "Carrozzeria Doninelli", "ind": "Via Giuseppe Garibaldi, 7, 20057 Assago MI", "lat": 45.406, "lng": 9.131}]
        e = decidi(esito(geo, posti), ("DONINELLI SRL", "VIA GARIBALDI 7", "20090", "ASSAGO", "MI"), None)
        self.assertEqual((e["stato"], e["lat"]), ("ok", 45.406))

    def test_omonimo_lontano_stessa_via(self):
        # «AutoRimessa Fogazzaro» in Via Fogazzaro 31 a Villa d'Alme' (BG) non e' Fogazzaro Garage di Milano
        geo = {"ordine": {"lat": 45.4609, "lng": 9.2093, "tipo": "ROOFTOP", "ind": "Via Antonio Fogazzaro, 31, 20135 Milano MI, Italia"}}
        posti = [{"nome": "AutoRimessa Fogazzaro", "ind": "Via Fogazzaro, 31, 24018 Villa d'Almè BG", "lat": 45.75, "lng": 9.61}]
        e = decidi(esito(geo, posti), ("FOGAZZARO GARAGE SRL", "VIA FOGAZZARO ANTONIO 31", "20135", "MILANO", "MI"), None)
        self.assertEqual((e["fonte"], e["lat"]), ("google-indirizzo", 45.4609))

    def test_indirizzo_in_comune_sbagliato_non_basta(self):
        # Via Mascagni 16 di Lainate geocodificata a Busto Garolfo: va scelta l'attivita' allo stesso indirizzo a Lainate
        geo = {"ordine": {"lat": 45.57, "lng": 8.88, "tipo": "ROOFTOP", "ind": "Via mascagni, 16, 20020 Busto Garolfo MI, Italia"}}
        posti = [{"nome": "Td Gomme", "ind": "Via Pietro Mascagni, 16, 20045 Lainate MI", "lat": 45.57, "lng": 9.03}]
        e = decidi(esito(geo, posti), ("T.D.GOMME DI TONONI DAVID", "VIA MASCAGNI 16", "20020", "LAINATE", "MI"), None)
        self.assertEqual((e["stato"], e["lng"]), ("ok", 9.03))


if __name__ == "__main__":
    unittest.main()
