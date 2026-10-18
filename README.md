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
- Database e pagina contengono **2025 e 2026** (`PAGINA_DAL` in `data/build.py`).
  Riepilogo, Fermi e Prodotti lavorano sull'anno corrente; la sezione **Confronto**,
  l'Andamento e la scheda cliente mettono a fianco i due anni.
- **Parità di periodo:** l'anno precedente viene confrontato fino allo stesso giorno
  dell'ultimo ordine caricato (es. 1 gen–1 ott); il resto dell'anno precedente è
  mostrato a parte ("dopo il gg/mm") ed è la base della vista "Ultimo trimestre".
- Sezione Confronto, sei viste: sintesi dei due anni; clienti in calo e in
  crescita (o tutti, per valore); persi e nuovi; mix prodotto (chi ha smesso, chi
  ha iniziato, chi non ha mai comprato una categoria); ultimo trimestre (chi
  ordinava un anno fa); per network (un tocco sulla riga apre i suoi clienti).
  Tutte filtrabili per provincia, network e tipo cliente.
- Il **totale dell'anno precedente** per cliente compare nella scheda, nel
  Riepilogo, nei Fermi e nelle viste di confronto. La ricerca clienti accetta
  anche il nome del network.
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

## Telefonate nella scheda cliente (dal 2026-10-16)

La scheda cliente ha una sezione **Telefonate**: le telefonate registrate con Plaud e abbinate al cliente (archivio `Mak/Plaud Note Pro/callrec.db`, letto in sola lettura). Per ognuna c'è la scheda completa del template «Chiamata cliente MAK» (richiesta, domande e risposte, dati tecnici, prodotti e prezzi, obiezioni, cosa devo fare, esito, nota personale, occasioni) e il link per aprirla in Plaud. Compaiono anche i clienti con telefonate ma senza ordini B2B nel periodo; la ricerca mostra quante telefonate ha ogni cliente. Le telefonate non ancora abbinate a un cliente non ci sono: si abbinano con `abbina.py` nel progetto Plaud.

**Aggiornamento ogni sera.** `Mak/Plaud Note Pro/notturno.sh` (20:00) lancia `data/pubblica.py`:
- rigenera la pagina con la passphrase dal Portachiavi (`mak-ordini-pass`);
- la pubblica solo se ordini o telefonate sono cambiati;
- se l'ultimo commit è una build automatica, lo sostituisce (`--amend` + `push --force-with-lease`), così il repository non accumula una copia da 2 MB a sera. Le modifiche al codice restano commit normali.

```bash
python3 data/pubblica.py                   # build + pubblicazione se i dati sono cambiati
python3 data/pubblica.py --non-pubblicare  # solo build
```

## Mappa sensori (dal 2026-10-18)

La sezione **Mappa** mostra su OpenStreetMap i clienti che hanno comprato sensori TPMS
dal 2025 (righe della categoria `TPMS / MATE`):

- **blu = Autel** (`MX UNIVERSAL` = MX-Sensor, `TPMS AUTEL 1SENS`); **rosso = MATE / Huf**
  (`MULTISENS`, `MULTIS.`, `MULT.TPMS`, `HUF`, `TPMS SI2024/SI2048/SI2076` che sono Huf);
  **grigio** = solo altri sensori (BEA019, PS8608, retrofit…). I `REPLAC.KIT 4 VALVE`
  (kit valvole di ricambio) non contano. Regole in testa a `data/build.py`.
- **Colore = marca dell'ultimo ordine** Autel o MATE/Huf: chi è passato da una marca
  all'altra prende la nuova. Ordine misto: vince la marca con più pezzi (parità → MATE).
- **Sbiadito** = nessun ordine di sensori da oltre 180 giorni rispetto all'ultimo ordine
  caricato. **Bordo tratteggiato** = posizione da verificare (vedi sotto).
- Il tocco sul pallino apre l'ultimo ordine di sensori: data, numero, righe, importo.
- Interruttori Autel / MATE-Huf / Altri con i conteggi. La vista iniziale inquadra
  MI/MB/LO; i clienti fuori zona (es. Torino) ci sono ma vanno cercati spostando la mappa.
- Leaflet 1.9.4 è inserito nella pagina dal build (`data/vendor/`, niente CDN); lo sfondo
  stradale arriva da OpenStreetMap e senza rete non si vede (i pallini sì).

**Coordinate** (`data/coordinate.py`, rifatte il 2026-10-18). Le coordinate delle mappe del
CRM sono risultate **inaffidabili**: per 327 clienti su 497 il punto era a più di 2 km
dall'officina, anche con l'indirizzo giusto. Ora vale **dove sta l'officina** (scelta di Stefano):

1. per ogni cliente si geocodifica con Google l'indirizzo dell'ordine e, se diverso,
   quello del CRM, e si cerca l'attività su Google Places per ragione sociale + città;
2. si usa il punto dell'attività Google, in quest'ordine: stesso nome e stessa via +
   civico; attività entro 300 m; stesso nome entro 1,5 km; stessa via + civico + comune;
   stesso nome nello stesso comune. Si confronta il **testo** dell'indirizzo perché nel DB
   il CAP è spesso quello vecchio (20090, 20010, 20020…) e Google Geocoding mette
   l'indirizzo nel comune sbagliato (Assago → Cesano Boscone, Lainate → Busto Garolfo);
3. senza attività riconoscibile: l'indirizzo dell'ordine, se preciso al civico e nel
   comune giusto; altrimenti il cliente va in `data/log/coordinate_da_controllare.md`
   (punto provvisorio, bordo tratteggiato sulla mappa);
4. le correzioni a mano vanno in `data/log/coordinate_manuali.json` e vincono su tutto
   (`"provvisorio": true` = ancora da confermare).

Esito al 2026-10-18: 573 clienti verificati in automatico, 4 decisi a mano (Corsico
Ricambi, Auto Randazzo, Alfa Service Auto, Lorenzo Gomme con sede legale a Taranto),
5 provvisori da confermare con Stefano.

I clienti nuovi si verificano da soli al build (massimo 60 per giro). Chiave
`GOOGLE_MAPS_API_KEY` dall'ambiente o da `Mak/nuove-aperture/.env`; senza chiave si
torna a CRM + OpenStreetMap. Costo: la ricerca chiede solo nome, indirizzo e posizione
(fascia **Text Search Pro**, soglia gratuita propria, distinta dalla fascia Enterprise del
giro nuove aperture) più Geocoding. La verifica completa del 2026-10-18 ha usato circa 600 Text
Search Pro e 690 Geocoding. Non rilanciare `--tutti` senza motivo: ripaga tutto; per
cambiare le regole basta `--ridecidi`, che lavora sui dati Google già salvati.

```bash
python3 data/coordinate.py --verifica          # verifica i clienti non ancora verificati
python3 data/coordinate.py --verifica --tutti  # rifà tutto (chiamate Google)
python3 data/coordinate.py --ridecidi          # rifà le scelte dai dati salvati (gratis)
python3 data/coordinate.py --mancanti          # riepilogo + elenco da controllare
```

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
| `data/build.py` | Dataset minimizzato → cifratura → `index.html`; classifica i sensori per la mappa. |
| `data/coordinate.py` | Coordinate dei clienti per la mappa: correzioni a mano → verifica Google (officina + indirizzo) → CRM/OpenStreetMap. |
| `data/vendor/` | Leaflet 1.9.4 (JS + CSS), inserito inline nella pagina dal build. |
| `index.template.html` | Web app (HTML/CSS/JS inline, nessuna CDN). |
| `index.html` | **Generato.** Unico file con dati, cifrati. |
| `tests/` | Test del parser, della classificazione sensori e delle regole delle coordinate. |

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
- Per la mappa entrano nel dataset cifrato le **coordinate** dei clienti con sensori
  (5 decimali): di fatto indicano l'indirizzo, quindi sono protette dalla passphrase come
  il resto. L'indirizzo in testo resta solo nel DB locale. Per la verifica, indirizzo e
  ragione sociale dell'officina vanno a Google Maps (sono dati pubblici dell'attività).

## Test

```bash
python3 -m unittest discover -s tests
```

I testi di prova sono inventati: nel repo non devono entrare dati di clienti veri.
