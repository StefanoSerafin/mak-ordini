-- Database locale ordini B2B (non pubblicato, ignorato da git).

CREATE TABLE IF NOT EXISTS clienti (
    codice          TEXT PRIMARY KEY,      -- 6 cifre con zeri, come COD. in MAK 2026.xlsx
    ragione_sociale TEXT,
    citta           TEXT,
    provincia       TEXT,
    cap             TEXT,
    indirizzo       TEXT,
    piva            TEXT,
    cod_fiscale     TEXT,
    cod_network     TEXT,
    network         TEXT,                  -- dal corpo della notifica (non e' nel PDF)
    tipo            TEXT,                  -- es. Gommisti, Officine - Carrozzerie
    flag_cliente    TEXT,                  -- (R)/(F)/(I)/(X) accanto all'indirizzo nel PDF; significato non noto
    in_anagrafica   INTEGER DEFAULT 0,
    primo_ordine    TEXT,
    ultimo_ordine   TEXT
);

CREATE TABLE IF NOT EXISTS ordini (
    id                TEXT PRIMARY KEY,    -- Riferimento Interno, es. I_797262
    codice_cliente    TEXT NOT NULL REFERENCES clienti(codice),
    data_ora          TEXT,
    inserito_da       TEXT,                -- agente | cliente | altro
    utente_raw        TEXT,
    kit_completo      INTEGER DEFAULT 0,
    termini_pagamento TEXT,
    vettore           TEXT,
    omaggio           INTEGER DEFAULT 0,   -- termini di pagamento "...OMAGGI": in pagina vale 0
    nota              TEXT,                -- riferimento libero dopo l'ID e "Note Carrello" (solo DB locale)
    merce_righe       REAL,                -- somma importi di riga: e' il valore ordine usato ovunque
    merce             REAL,                -- "Importo Merce" del PDF (non sempre presente)
    spedizione        REAL,
    pfu               REAL,
    contrassegno      REAL,
    altri_costi       REAL,
    imponibile        REAL,
    iva               REAL,
    totale            REAL,
    quadra            INTEGER,             -- 1 se somma righe = imponibile - spedizione - pfu - contrassegno - altri
    pagine            INTEGER,
    pdf               TEXT
);

CREATE TABLE IF NOT EXISTS righe (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ordine_id    TEXT NOT NULL REFERENCES ordini(id),
    n_riga       INTEGER,
    cod_articolo TEXT,
    descrizione  TEXT,
    applicazione TEXT,
    coupon       TEXT,
    qta          REAL,
    prezzo       REAL,
    sconto       TEXT,
    importo      REAL,
    categoria    TEXT
);

CREATE TABLE IF NOT EXISTS scarti (
    origine     TEXT,                      -- mail | pdf
    riferimento TEXT,
    motivo      TEXT,
    data        TEXT
);

CREATE INDEX IF NOT EXISTS ix_ordini_cliente ON ordini(codice_cliente);
CREATE INDEX IF NOT EXISTS ix_ordini_data    ON ordini(data_ora);
CREATE INDEX IF NOT EXISTS ix_righe_ordine   ON righe(ordine_id);
CREATE INDEX IF NOT EXISTS ix_righe_articolo ON righe(cod_articolo);
CREATE INDEX IF NOT EXISTS ix_righe_cat      ON righe(categoria);

-- Preventivi fatti con la webapp mak-preventivi (dal 2026-10-24): arrivano dall'archivio privato
-- Mak/mak-preventivi-dati con data/preventivi.py importa; l'esito lo calcola data/preventivi.py esiti.
CREATE TABLE IF NOT EXISTS preventivi (
    id             TEXT PRIMARY KEY,       -- AAAAMMGG-hhmmss-xxxx, dato dalla webapp
    data_ora       TEXT,                   -- ISO, ora italiana
    cliente_codice TEXT,                   -- 6 cifre; vuoto = da abbinare
    cliente_nome   TEXT,                   -- come scelto o scritto nella webapp
    abbinato       TEXT,                   -- app | nome | manuale | '' (come si è arrivati al codice)
    vettura        TEXT,                   -- testo leggibile (marca modello anno)
    vettura_json   TEXT,                   -- dettaglio della vettura com'era nella webapp
    diametri       TEXT,                   -- diametri delle ruote proposte, es. "16,17"
    listino        TEXT,
    tpms           TEXT,                   -- JSON del TPMS scelto, o vuoto
    esito          TEXT,                   -- riuscito | riuscito_altra_ruota | non_riuscito | in_corso | da_abbinare
    esito_ordine   TEXT,                   -- id dell'ordine che ha dato l'esito
    esito_data     TEXT,
    importato      TEXT                    -- quando è stato caricato/aggiornato
);

CREATE TABLE IF NOT EXISTS preventivi_articoli (
    preventivo_id    TEXT NOT NULL REFERENCES preventivi(id),
    n                INTEGER,
    codice_articolo  TEXT,                 -- codice dell'ordine B2B (per l'acciaio F…, non R1-…)
    code             TEXT,                 -- codice mostrato nella webapp (per l'acciaio R1-…)
    tipo             TEXT,                 -- lega | acciaio | ruotino | accessorio
    modello          TEXT,
    finitura         TEXT,
    misure           TEXT,
    diametro         TEXT,
    netto            REAL,
    listino_pubblico REAL,
    accessori        REAL
);

CREATE INDEX IF NOT EXISTS ix_prev_cliente  ON preventivi(cliente_codice);
CREATE INDEX IF NOT EXISTS ix_prev_art      ON preventivi_articoli(preventivo_id);
CREATE INDEX IF NOT EXISTS ix_prev_articolo ON preventivi_articoli(codice_articolo);
