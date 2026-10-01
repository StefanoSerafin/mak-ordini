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
