"""Test delle chat WhatsApp nel database (data/carica_whatsapp.py) su dati INVENTATI: questo repo è pubblico.

    python3 -m unittest discover -s tests
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(QUI, "..", "data"))
import carica_whatsapp as W  # noqa: E402

ESTRATTORE = os.path.normpath(os.path.join(QUI, "..", "..", "mak-chat-extractor"))


@unittest.skipUnless(os.path.exists(os.path.join(ESTRATTORE, "qa_whatsapp.py")), "mak-chat-extractor assente")
class TestCaricaWhatsapp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        cartella = os.path.join(self.tmp, "WhatsApp Chat - GOMME PROVA SRL")
        os.makedirs(cartella)
        with open(os.path.join(cartella, "_codice.txt"), "w") as f:
            f.write("000111\n")
        self.db = os.path.join(self.tmp, "chat.db")
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE chats (id INTEGER PRIMARY KEY, client_name TEXT, source TEXT)")
        con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, chat_id INTEGER, line_no INTEGER, dt TEXT,"
                    " sender TEXT, is_owner INTEGER, kind TEXT, text TEXT)")
        con.execute("CREATE TABLE attachments (id INTEGER PRIMARY KEY, chat_id INTEGER, att_kind TEXT)")
        con.execute("INSERT INTO chats VALUES (1, 'GOMME PROVA SRL', ?)", (cartella,))
        con.execute("INSERT INTO chats VALUES (2, 'SENZA CODICE', ?)", (os.path.join(self.tmp, "nessuna"),))
        msg = [(1, 1, "2025-03-04T08:00:00", 1, "broadcast", "PROMO DEL MARTEDI"),
               (1, 2, "2025-03-04T09:00:00", 0, "client_msg", "Hai il ruotino per la Panda?"),
               (1, 3, "2025-03-04T09:06:00", 1, "owner_msg", "Sì, mandami il libretto"),
               (1, 4, "2025-03-05T10:00:00", 0, "client_msg", "Quanto costa il kit?"),
               (2, 5, "2025-03-05T10:00:00", 0, "client_msg", "Mi chiami?")]
        con.executemany("INSERT INTO messages (chat_id, line_no, dt, is_owner, kind, text) VALUES (?,?,?,?,?,?)", msg)
        con.execute("INSERT INTO attachments (chat_id, att_kind) VALUES (1, 'client_photo')")
        con.commit()
        con.close()

    def test_raccogli(self):
        clienti, domande, senza_codice = W.raccogli(self.db)
        self.assertEqual(senza_codice, 1)
        self.assertEqual(list(clienti), ["000111"])
        c = clienti["000111"]
        self.assertEqual(c[1], "2025-03-04")            # primo messaggio
        self.assertEqual(c[4], 2)                       # messaggi del cliente, broadcast esclusi
        self.assertEqual(c[6], 1)                       # una foto
        self.assertEqual((c[8], c[9]), (1, 1))          # una domanda con risposta, una senza
        self.assertEqual(domande[0][2], "Hai il ruotino per la Panda?")
        self.assertEqual(domande[0][4], 6.0)
        self.assertIn("ruotino e kit NPK", json.loads(domande[0][5]))

    def test_libretti(self):
        p = os.path.join(self.tmp, "libretti.json")
        with open(p, "w") as f:
            json.dump([{"codice": "000111", "marca": "FIAT", "modello": "PANDA", "pneumatici": ["175/65 R14 82T"],
                        "leggibile": True}], f)
        r = W.libretti(p)
        self.assertEqual(r[0][6], "175/65 R14 82T")
        self.assertEqual(r[0][7], 1)
        self.assertEqual(W.libretti(os.path.join(self.tmp, "manca.json")), [])


if __name__ == "__main__":
    unittest.main()
