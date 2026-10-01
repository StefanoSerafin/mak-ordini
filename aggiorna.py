#!/usr/bin/env python3
"""Aggiorna il database ordini: Mail -> PDF -> SQLite -> index.html cifrato.

    python3 aggiorna.py               # ordini nuovi + rigenera la pagina
    python3 aggiorna.py --no-build    # solo database, senza rigenerare la pagina
    python3 aggiorna.py --completo    # riscorre tutti i messaggi del periodo
    python3 aggiorna.py --no-mail     # non interroga Mail: ricarica dai PDF gia' scaricati

Mail deve essere aperta. Legge solo la casella "Ordini" dell'account MAK, dal
2026-01-01. La passphrase per il build si prende da MAK_ORDINI_PASS oppure
viene chiesta a terminale (non viene mai salvata).
"""
import argparse
import datetime
import os
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(QUI, "data"))
import build as mod_build      # noqa: E402
import carica_db               # noqa: E402
import estrai_mail             # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dal", default=estrai_mail.DAL_MINIMO.isoformat())
    ap.add_argument("--completo", action="store_true")
    ap.add_argument("--no-mail", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()

    e = None
    if not a.no_mail:
        print("1/3 Estrazione da Mail")
        e = estrai_mail.estrai(datetime.date.fromisoformat(a.dal), completo=a.completo)

    print("2/3 Caricamento nel database")
    con, cfg = carica_db.apri(), carica_db.carica_regole()
    ok, ko = carica_db.carica(con, cfg)
    carica_db.segna_anagrafica(con)
    carica_db.applica_profili(con)
    r = carica_db.report(con)

    if not a.no_build:
        print("3/3 Build della pagina cifrata")
        mod_build.build()

    print("\n=== Riepilogo ===")
    if e:
        print(f"Messaggi letti: {e['letti']} | PDF nuovi: {e['salvati']} | errori Mail: {e['errori']} | "
              f"messaggi scartati (totale): {e['scarti']}")
    print(f"Ordini nuovi caricati: {ok} | PDF non leggibili: {ko}")
    print(f"Totale: {r['ordini']} ordini, {r['clienti']} clienti, merce {r['merce']:.2f}")
    print(f"Ordini che non quadrano: {len(r['non_quadrano'])} | righe in 'Altro': {r['quota_altro']}% della merce")
    if r["non_quadrano"]:
        print("  " + ", ".join(r["non_quadrano"][:20]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
