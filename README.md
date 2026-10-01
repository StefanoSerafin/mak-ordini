# mak-ordini — database ordini clienti dal B2B

Legge da Mail le notifiche "Nuovo Ordine" del portale B2B, estrae dal PDF
allegato testata e righe di ogni ordine, le salva in un database SQLite locale
e genera una web app single-file **cifrata** per consultare gli ordini per
cliente (da Mac, iPhone, iPad).

**Online:** https://stefanoserafin.github.io/mak-ordini/ (serve la passphrase)

## Fonte e limiti

- **Fonte unica:** casella `Ordini` dell'account `MAK` in Mail, **dal
  01/01/2025**. Lo script non legge altre caselle né messaggi più vecchi (il
  limite è cablato in `data/estrai_mail.py`, `DAL_MINIMO`).
- Le notifiche vanno spostate in `Ordini` a mano: un ordine rimasto in Posta in
  arrivo non viene visto finché non lo sposti.
- Il database contiene 2025 e 2026. La **pagina mostra solo il 2026** (`PAGINA_DAL`
  in `data/build.py`), finché non ci sono le viste di confronto tra i due anni.
- Sono **ordini, non fatture**: resi, note di credito e modifiche fatte dopo
  l'ordine non compaiono. I totali sono "ordinato", non "fatturato".
- Importo di riferimento = **merce** (somma delle righe), senza IVA, spedizione,
  PFU e contrassegno.
- **Network e tipo cliente** (Driver, Asconauto, Gommisti, Officine…) non sono
  nel PDF: si leggono dall'inizio del corpo della notifica e finiscono in
  `data/log/profili.json`. Per ogni cliente vale l'ordine più recente.
- Gli **omaggi** (termini di pagamento "…OMAGGI") restano visibili con il badge
  "omaggio" ma valgono 0 nei totali.
- "Inserito da": tu (`s.serafin`), il cliente (`clNNNNNN.xx`) oppure la sede/un
  collega (qualsiasi altro utente).
- Il parser riconosce tre layout di PDF: italiano standard, italiano compatto
  (`Rif.Interno:`), inglese (`Internal Reference`).
- Il suffisso `(R)/(F)/(I)/(X)` accanto all'indirizzo nel PDF è salvato come
  `flag_cliente`; il significato non è noto e non incide sui totali.

## Uso

```bash
python3 aggiorna.py              # ordini nuovi da Mail + database + pagina
python3 aggiorna.py --no-build   # senza rigenerare la pagina
python3 aggiorna.py --no-mail    # ricarica dai PDF già scaricati
python3 aggiorna.py --completo   # riscorre tutti i messaggi del periodo
python3 data/estrai_mail.py --profili   # completa network/tipo degli ordini già scaricati
```

Mail deve essere aperta. Il build chiede la **passphrase** (oppure la legge da
`MAK_ORDINI_PASS`); minimo 16 caratteri.

Dipendenze: `pip3 install pdfplumber cryptography openpyxl`.

Dopo un'interruzione basta rilanciare con `--completo`: i messaggi già trattati
(`data/log/messaggi.json`) scorrono senza essere riscaricati.

**Appoggio temporaneo:** durante il download compare in `~/Downloads` una cartella
`makordini_tmp_…`, rimossa a fine giro. Serve perché Mail è in sandbox: in Download
scrive per diritto proprio, mentre nelle cartelle temporanee di sistema smette dopo
circa 1.800 salvataggi (errore -10000 sui permessi) fino al riavvio di Mail.

**Se Mail sembra bloccata:** una richiesta AppleScript andata in timeout continua
a girare dentro Mail e rallenta tutte le successive. Aspetta qualche minuto, o
chiudi e riapri Mail, poi rilancia.

## Struttura

| File | Ruolo |
|---|---|
| `aggiorna.py` | Punto di ingresso: estrazione → caricamento → build. |
| `data/estrai_mail.py` | Pilota Mail via AppleScript, salva i PDF in `data/pdf/I_<n>.pdf`. |
| `data/parse_pdf.py` | Da PDF a testata + righe + totali. |
| `data/schema.sql` | Schema SQLite (`clienti`, `ordini`, `righe`, `scarti`). |
| `data/carica_db.py` | Carica i PDF nuovi in `data/ordini.db`, classifica, controlla la quadratura. |
| `data/categorie.json` | Regole articolo → categoria (vince la prima che corrisponde). |
| `data/build.py` | Dataset minimizzato → cifratura → `index.html`. |
| `index.template.html` | Web app (HTML/CSS/JS inline, nessuna CDN). |
| `index.html` | **Generato.** Unico file con dati, cifrati. |
| `tests/` | Test del parser su testi sintetici. |

Non versionati (`.gitignore`): `data/pdf/`, `data/ordini.db`, `data/log/`,
`data/ordini.plain.json`.

## Pubblicare un aggiornamento

```bash
python3 aggiorna.py                 # chiede la passphrase e rigenera index.html
git add index.html && git commit -m "Pagina ordini: build AAAA-MM-GG" && git push
```

GitHub Pages si aggiorna in un paio di minuti.

## Categorie

Modifica `data/categorie.json`, poi:

```bash
python3 data/carica_db.py --riclassifica
```

`data/log/categorie_frequenza.csv` elenca, per prefisso di codice articolo, la
categoria assegnata, i volumi e tre descrizioni di esempio: serve per vedere
cosa finisce in "Altro".

## Sicurezza

- `index.html` contiene il dataset cifrato con AES-GCM-256; la chiave deriva
  dalla passphrase con PBKDF2-SHA256 (600.000 iterazioni). Senza passphrase la
  pagina non mostra nulla.
- Il file è pubblico: la protezione **è** la passphrase. Per questo `build.py`
  ne rifiuta una più corta di 16 caratteri (un PIN di 4 cifre si forza offline in
  pochi minuti).
- Nel dataset pubblicato **non** entrano: P.IVA, codice fiscale, via, CAP,
  termini di pagamento, note d'ordine. Restano solo nel DB locale.
- "Ricorda su questo dispositivo" salva la passphrase nel `localStorage` di quel
  browser. In fondo alla pagina c'è il link per dimenticarla.
- La decifratura richiede `https://` o `http://localhost` (non `file://`). Per
  provarla in locale: `python3 -m http.server` e apri `http://localhost:8000/`.
- Cambiare passphrase: rilancia `python3 data/build.py` con quella nuova. I
  vecchi `index.html` restano nella storia git, cifrati con la vecchia.
- Da `Mak/MAK 2026.xlsx` si leggono solo le colonne `CLIENTE` e `COD.`.

## Test

```bash
python3 -m unittest discover -s tests
```

I testi di prova sono inventati: nel repo non devono entrare dati di clienti veri.
