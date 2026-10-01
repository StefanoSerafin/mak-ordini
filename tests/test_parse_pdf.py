"""Test del parser su testi SINTETICI (nomi, indirizzi e partite IVA inventati:
questo repo e' pubblico, qui non devono comparire dati di clienti veri)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
from parse_pdf import OrdineNonValido, parse_testo  # noqa: E402
from carica_db import carica_regole, categoria  # noqa: E402

TESTATA = """Data - Ora: 01/10/2026 11:53:37
Pagina
1/1
Utente: {utente}
Riferimento Interno
{id}
Cliente OFFICINA PROVA SNC Cod. Cli. MAK 000123 01
{flag}VIA DEI TEST 1 Cod. Cli. Net. {net}Agente SS
20100 PAESE DI PROVA MI IT
Partita Iva 00000000000 Termini di Pagamento RICEVUTA 30 GG F.M.
Codice Fiscale 00000000000 Modalità Consegna PORTO FRANCO
Codice Cliente 000123 Spedizione VETTORE
Tipo Consegna STANDARD Vettore
Cod.Articolo Descrizione Qtà Prezzo Sconti Importo
"""


def ordine(corpo, utente="s.serafin", id_="I_100001", flag="", net=""):
    return TESTATA.format(utente=utente, id=id_, flag=flag, net=net) + corpo


SEMPLICE = ordine("""F4540CCSI90A1 4,5J14 ACC 1875/A1 ET90 5X139 110SI RO 1,00 120,00 120,00
78K000R441 NPK441 1258016 510057,1 0 JP4 K17 1,00 143,00 143,00
SKODA, SCALA, 2019 > NW
Importo Totale 332.94
Importo PFU 1.9
Importo Merce 263.00
Costi di Spedizione 8.00
Importo Imponibile 272.90
Imposta (Iva) 60.04
ORDINE 1
""")

SCONTO = ordine("""8000008501 KIT 20 BOLT B0046-007 16X1,5X29 C60 1,00 34,00 34,00
7800000EZD NPK EZ DRIVE - ACCESSORY KIT 3,00 99,00 38.00 184,14
Importo Totale 275.89
Importo Merce 218.14
Costi di Spedizione 8.00
Importo Imponibile 226.14
Imposta (Iva) 49.75
ORDINE 1
""", utente="cl000123.op", flag="(F) ")

KIT = ordine("""Kit Completo Cerchi + Pneumatici + Accessori
HYUNDAI, I20, 2020 >, BC3
F6060BRTM45CM3X 6J16 DAVINCI/CM3X E45 4X100 54,1 LT IT 4,00 111,75 447,00
8050000907 NUT SET N250421-C 1,00 10,00 10,00
93000000MXG VALVE TPMS MX UNIVERS. GOMMA/RUBBER 4,00 19,09 76,36
791NEX082318A 195/55R16 87T NEXEN 195/55R16 87T 4,00 78,20 312,80
79200000000 MONTAGGIO/BILANCIATURA 1,00 15,00 15,00
Importo Totale 1059.89
Importo PFU 7.6
Importo Imponibile 868.76
Imposta (Iva) 191.13
ORDINE 1
""", utente="cl000123.op", net="4698H ")

CONTRASSEGNO = ordine("""930000MP6M VALVE MATE MULTISENS TPMS MP6METAL [Cod. Coupon: R] 20,00 15,90 318,00
Importo Totale 403.82
Costo Contrass. 5.00
Importo Merce 318.00
Costi di Spedizione 8.00
Importo Imponibile 331.00
Imposta (Iva) 72.82
ORDINE 1
""")

SENZA_MERCE = ordine("""F8590KAGB42WS3X 8,5J19 KASSE/WS3X E42 5112 66,45 GB IT 4,00 185,80 743,20
AUDI, A5 (F2) - A5 AVANT (F2), 2024 > F2
Importo Totale 906.70
Importo Imponibile 743.20
Imposta (Iva) 163.50
ORDINE 1
""", utente="ufficio.xy")

MIGLIAIA = ordine("""F8590KAGB42WS3X 8,5J19 KASSE/WS3X E42 5112 66,45 GB IT 8,00 185,80 1.486,40
Importo Totale 1813.41
Importo Imponibile 1486.40
Imposta (Iva) 327.01
ORDINE 1
""")


A_CAPO = ordine("""8000000938 RING SET B225L27519 1,00 12,00 12,00
930000ECSM VALVE TPMS HUF ECS 1430 METAL [Cod. Coupon: B] 15,00 13,95 209,25
FIAT, PANDA, 2012 > 319
VALVE TPMS HUF ECS 1432 METAL BLACK [Cod. Coupon: B]
93000ECSBM 10,00 13,95 139,50
Importo Totale 440.52
Importo Imponibile 360.75
Imposta (Iva) 79.77
ORDINE 1
""")

INGLESE = """Date - Time: 19/02/2026 17:00:37
Page 1/1
User: cl000123.op
Internal Reference I_100002
Customer OFFICINA PROVA SNC 000123 01
VIA DEI TEST 1 Sales Rep. SS
20100 PAESE DI PROVA MI IT
VAT Code 00000000000 Payment Terms CONTRASSEGNO CON ASSEGNO BANC.
Fiscal Code 00000000000 Delivery Terms PORTO FRANCO
Customer Code 000123 Shipment VETTORE
Shipment Method STANDARD Carrier CORRIERE PROVA SRL
PAGAMENTO ALLA CONSEGNA. Accettare anche titoli bancari a noi intestati
WARNING
e datati dal Cliente Non trasferibili Euro: 81.83
Item Code Description Qty Your Pricelist Discounts Amount
F6550CCSI42GG4X 6,5J15 AC2056/GG4X ET42 5X108 65 SI RO 1,00 50,07 50,07
FIAT, DOBLO (M1), 2023 > E
Total Amount 81.83
Costo Contrass. 5.00
Total amount of goods 50.07
Shipment cost 12.00
Taxable Amount 67.07
VAT (If applicable) 14.76
ORDINE 1
"""


class TestParser(unittest.TestCase):
    def test_descrizione_a_capo(self):
        o = parse_testo(A_CAPO)
        self.assertEqual(len(o["righe"]), 3)
        self.assertEqual(o["righe"][1]["applicazione"], "FIAT, PANDA, 2012 > 319")
        r = o["righe"][2]
        self.assertEqual((r["cod_articolo"], r["descrizione"], r["coupon"], r["importo"]),
                         ("93000ECSBM", "VALVE TPMS HUF ECS 1432 METAL BLACK", "B", 139.50))
        self.assertAlmostEqual(sum(x["importo"] for x in o["righe"]), 360.75)

    def test_descrizione_a_capo_dopo(self):
        o = parse_testo(ordine("""93000TR413 N.100 VALVE TR413 2,00 12,50 25,00
9300000335 1,00 7,80 7,80
KIT N.50X12 PESI ADESIVI SILVER 5GR
Importo Totale 40.02
Importo Imponibile 32.80
Imposta (Iva) 7.22
ORDINE 1
"""))
        self.assertEqual(len(o["righe"]), 2)
        self.assertEqual(o["righe"][1]["descrizione"], "KIT N.50X12 PESI ADESIVI SILVER 5GR")
        self.assertIsNone(o["righe"][0]["applicazione"])
        self.assertIsNone(o["righe"][1]["applicazione"])

    def test_pdf_in_inglese(self):
        o = parse_testo(INGLESE)
        self.assertEqual((o["id"], o["codice_cliente"], o["data_ora"]), ("I_100002", "000123", "2026-02-19 17:00:37"))
        self.assertEqual(o["ragione_sociale"], "OFFICINA PROVA SNC")
        self.assertEqual((o["indirizzo"], o["citta"], o["provincia"]), ("VIA DEI TEST 1", "PAESE DI PROVA", "MI"))
        self.assertEqual(o["termini_pagamento"], "CONTRASSEGNO CON ASSEGNO BANC.")
        self.assertEqual(o["vettore"], "CORRIERE PROVA SRL")
        self.assertEqual(len(o["righe"]), 1)
        self.assertEqual(o["righe"][0]["applicazione"], "FIAT, DOBLO (M1), 2023 > E")
        self.assertEqual((o["merce"], o["spedizione"], o["contrassegno"], o["imponibile"], o["totale"]),
                         (50.07, 12.0, 5.0, 67.07, 81.83))

    def test_semplice(self):
        o = parse_testo(SEMPLICE)
        self.assertEqual(o["id"], "I_100001")
        self.assertEqual(o["data_ora"], "2026-10-01 11:53:37")
        self.assertEqual(o["codice_cliente"], "000123")
        self.assertEqual(o["ragione_sociale"], "OFFICINA PROVA SNC")
        self.assertEqual((o["cap"], o["citta"], o["provincia"]), ("20100", "PAESE DI PROVA", "MI"))
        self.assertEqual(o["indirizzo"], "VIA DEI TEST 1")
        self.assertEqual(o["inserito_da"], "agente")
        self.assertEqual(o["termini_pagamento"], "RICEVUTA 30 GG F.M.")
        self.assertIsNone(o["flag_cliente"])
        self.assertEqual(len(o["righe"]), 2)
        self.assertIsNone(o["righe"][0]["applicazione"])
        self.assertEqual(o["righe"][1]["applicazione"], "SKODA, SCALA, 2019 > NW")
        self.assertEqual(o["righe"][1]["descrizione"], "NPK441 1258016 510057,1 0 JP4 K17")
        self.assertAlmostEqual(sum(r["importo"] for r in o["righe"]), 263.00)
        self.assertEqual((o["merce"], o["spedizione"], o["pfu"], o["imponibile"]), (263.0, 8.0, 1.9, 272.9))

    def test_sconto_e_flag(self):
        o = parse_testo(SCONTO)
        self.assertEqual(o["flag_cliente"], "F")
        self.assertEqual(o["indirizzo"], "VIA DEI TEST 1")
        self.assertEqual(o["inserito_da"], "cliente")
        r = o["righe"][1]
        self.assertEqual((r["qta"], r["prezzo"], r["sconto"], r["importo"]), (3.0, 99.0, "38.00", 184.14))
        self.assertEqual(r["descrizione"], "NPK EZ DRIVE - ACCESSORY KIT")
        self.assertIsNone(o["righe"][0]["sconto"])

    def test_kit_completo(self):
        o = parse_testo(KIT)
        self.assertEqual(o["kit_completo"], 1)
        self.assertEqual(o["cod_network"], "4698H")
        self.assertEqual(len(o["righe"]), 5)
        self.assertTrue(all(r["applicazione"] == "HYUNDAI, I20, 2020 >, BC3" for r in o["righe"]))
        self.assertIsNone(o["merce"])
        self.assertAlmostEqual(sum(r["importo"] for r in o["righe"]), 861.16)

    def test_contrassegno_e_coupon(self):
        o = parse_testo(CONTRASSEGNO)
        self.assertEqual(o["contrassegno"], 5.0)
        self.assertEqual(o["righe"][0]["coupon"], "R")
        self.assertEqual(o["righe"][0]["descrizione"], "VALVE MATE MULTISENS TPMS MP6METAL")
        self.assertAlmostEqual(o["imponibile"] - o["spedizione"] - o["contrassegno"], 318.0)

    def test_senza_importo_merce(self):
        o = parse_testo(SENZA_MERCE)
        self.assertIsNone(o["merce"])
        self.assertIsNone(o["spedizione"])
        self.assertEqual(o["inserito_da"], "altro")
        self.assertEqual(o["righe"][0]["importo"], 743.20)
        self.assertEqual(o["righe"][0]["descrizione"], "8,5J19 KASSE/WS3X E42 5112 66,45 GB IT")

    def test_riferimento_con_nota(self):
        testo = SEMPLICE.replace("Riferimento Interno\nI_100001", "Riferimento Interno\nI_100001 Omaggio") \
                        .replace("Cod.Articolo", "Note Carrello + CARTELLINI\nCod.Articolo", 1)
        o = parse_testo(testo)
        self.assertEqual(o["id"], "I_100001")
        self.assertEqual(o["nota"], "Omaggio | + CARTELLINI")
        self.assertEqual(len(o["righe"]), 2)

    def test_variante_compatta(self):
        testo = """Data - Ora: 19/01/2026 11:30:51
Pag. 1/1
Utente: cl000123.op
Rif.Interno: I_100003
Cliente OFFICINA PROVA SNC 000123 01
(X) VIA DEI TEST 1 Agente SS
20100 PAESE DI PROVA MI IT
Partita Iva 00000000000 Pagamento RICEVUTA 30 GG F.M.
Codice Fiscale 00000000000 Modalità Consegna PORTO FRANCO
Codice Cliente 000123 Spedizione VETTORE
Tipo Consegna STANDARD Vettore
Cod.Articolo Descrizione Qtà Prezzo Sconti Importo
F1521MZGB67KY6 11,5J21 MONA-D/KY6 E67 5130 71,6 GB IT 1,00 400,56 400,56
Importo Totale 488.68
Imponibile 400.56
Imposta (Iva) 88.12
ORDINE 1
"""
        o = parse_testo(testo)
        self.assertEqual((o["id"], o["flag_cliente"], o["piva"]), ("I_100003", "X", "00000000000"))
        self.assertEqual(o["termini_pagamento"], "RICEVUTA 30 GG F.M.")
        self.assertEqual((o["imponibile"], o["righe"][0]["importo"]), (400.56, 400.56))

    def test_totale_a_cavallo_di_pagina(self):
        o = parse_testo(ordine("""F7070MMBM55P5IX 7J17 MAGMA/P5IX ET55 5X100 56,1 BLM IT 4,00 142,99 20.00 457,57
SUBARU, XV, 2018 > G5
Importo Totale 558.24
457.57
Importo Imponibile
ORDINE 1
Imposta (Iva) 100.67
ORDINE 2
"""))
        self.assertEqual((o["imponibile"], o["iva"], o["totale"]), (457.57, 100.67, 558.24))
        self.assertEqual(o["righe"][0]["applicazione"], "SUBARU, XV, 2018 > G5")

    def test_separatore_migliaia(self):
        self.assertEqual(parse_testo(MIGLIAIA)["righe"][0]["importo"], 1486.40)

    def test_pdf_non_valido(self):
        with self.assertRaises(OrdineNonValido):
            parse_testo("testo qualsiasi")
        with self.assertRaises(OrdineNonValido):
            parse_testo(ordine("Importo Totale 10.00\nORDINE 1\n"))


class TestCategorie(unittest.TestCase):
    def test_regole(self):
        cfg = carica_regole()
        casi = [
            ("F4540CCSI90A1", "4,5J14 ACC 1875/A1 ET90 5X139 110SI RO", "Ruote acciaio"),
            ("F6060CCMB36HA2X", "6J16 AC 1786/HA2X ET36 5X98 58,1 MB RO", "Ruote acciaio"),
            ("F7580KAGB49PE4X", "7,5J18 KASSE/PE4X E49 5X100 57,1 GB IT", "Ruote lega"),
            ("78K000R441", "NPK441 1258016 510057,1 0 JP4 K17", "Ruotino / kit NPK"),
            ("93000000MXG", "VALVE TPMS MX UNIVERS. GOMMA/RUBBER", "TPMS / MATE"),
            ("9300000330", "MATE ATEQ TESTER TOOL VT41/MA41", "Tool e diagnosi"),
            ("9300000335", "KIT N.50X12 PESI ADESIVI SILVER 5GR", "Bulloneria e accessori"),
            ("73000SSL04", "NPK MULTIGRIP LIGHT SNOW SOCKS TG04", "Calze da neve NPK"),
            ("791NEX082318A", "195/55R16 87T NEXEN 195/55R16 87T", "Pneumatici"),
            ("79200000000", "MONTAGGIO/BILANCIATURA", "Servizi"),
            ("F6060CCMB68D3", "6J16 ACCI 1909/D3 ET68 5X118 71 MB FR", "Ruote acciaio"),
            ("F7060CCSI46GG4X", "7J16 PS616003/GG4X ET46 5X108 65 SI FR", "Ruote acciaio"),
            ("F1175CCSI00X1", "11,75J22,5 15152G/X1 00 10X335 SILV", "Ruote truck"),
            ("9400000010", "AD-BLUE CISTERNA 1000 LT", "AdBlue"),
            ("7900000870", "GOMMA 135/90 R17", "Pneumatici"),
            ("7600000085", "DISTANZIALE XILEMA A295-B66SW COPPI", "Distanziali Xilema"),
            ("93000TR413", "N.100 VALVE TR413", "Bulloneria e accessori"),
            ("9300000123", "REPLAC.KIT 4 VALVE MATE RUBBER", "TPMS / MATE"),
            ("ZZZ", "QUALCOSA", "Altro"),
        ]
        for cod, desc, attesa in casi:
            self.assertEqual(categoria(cod, desc, cfg), attesa, cod)


if __name__ == "__main__":
    unittest.main()
