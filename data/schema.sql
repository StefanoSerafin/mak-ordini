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

-- Export del gestionale scaricati dal B2B (Mak/mak-export-b2b, dal 2026-10-28): fotografie complete,
-- riscritte per intero a ogni giro da data/carica_export.py.
CREATE TABLE IF NOT EXISTS gestionale_righe (
    ordine_id     TEXT,                    -- I_<numero>, come ordini.id
    st_ord        TEXT,                    -- stato ordine: SA saldato, AP aperto, EP parz. evaso, IA in approvazione
    dt_ord        TEXT,                    -- AAAA-MM-GG
    canale        TEXT,                    -- B2BCLI cliente, B2BAGE agente, B2BMAS/B2BAGC/*** sede o altro
    rif_cliente   TEXT,
    cod_cliente   TEXT,                    -- 6 cifre
    cod_articolo  TEXT,
    descrizione   TEXT,
    diametro      TEXT,
    qta_ord       REAL,
    dt_cons       TEXT,                    -- consegna prevista
    imp_ord       REAL,
    qta_spe       REAL,
    imp_spe       REAL,
    qta_res       REAL,                    -- ancora da spedire
    imp_res       REAL,
    st_riga       TEXT,
    auto_marca    TEXT,
    auto_modello  TEXT,
    mag           TEXT,
    categoria     TEXT                     -- da categorie.json, come righe.categoria
);
CREATE INDEX IF NOT EXISTS ix_gr_ordine  ON gestionale_righe(ordine_id);
CREATE INDEX IF NOT EXISTS ix_gr_cliente ON gestionale_righe(cod_cliente);

-- Anagrafica clienti del gestionale: SOLO le colonne della lista bianca di carica_export.py.
-- Mai utente/password B2B, telefoni, cellulari, email, indirizzi.
CREATE TABLE IF NOT EXISTS anagrafica_b2b (
    codice            TEXT PRIMARY KEY,    -- 6 cifre
    ragione_sociale   TEXT,
    tipo              TEXT,
    network           TEXT,
    network2          TEXT,
    localita          TEXT,
    provincia         TEXT,
    listino           TEXT,
    campagna          TEXT,
    pagamento         TEXT,
    b2b               INTEGER,             -- 1 accesso B2B attivo, 0 no, 2 altro (come nel gestionale)
    b2b_ultimo        TEXT,                -- ultimo accesso al B2B, AAAA-MM-GG; NULL = mai
    fatt_prec         REAL,                -- fatturato anno precedente (gestionale)
    fatt_corr         REAL,                -- fatturato anno corrente
    ult_acq_tpms      TEXT,                -- ultimo acquisto sensori TPMS universali, AAAA-MM-GG
    tool_tpms         TEXT,                -- marca dello strumento dichiarata
    tool_orange       TEXT,
    tool_autel        TEXT,
    tool_ateq         TEXT,
    obd               TEXT,
    whatsapp          TEXT,
    marca             TEXT,                -- marca auto (concessionari)
    priorita          TEXT,
    piva              TEXT,
    cod_fiscale       TEXT
);

-- Chat WhatsApp con i clienti (dal 2026-10-31): dal backup dell'iPhone via Mak/mak-chat-extractor
-- (backup_export.py -> extract.py -> mak_chat.db), caricate con data/carica_whatsapp.py.
-- Si riscrivono per intero a ogni caricamento. Testi in chiaro nel database; nella pagina cifrata dal 2026-10-31 (build.py whatsapp(), tagliati a 600 caratteri).
CREATE TABLE IF NOT EXISTS whatsapp_clienti (
    codice             TEXT PRIMARY KEY,   -- codice cliente del gestionale (da _codice.txt della cartella chat)
    primo_msg          TEXT,               -- AAAA-MM-GG
    ultimo_msg         TEXT,
    ultimo_msg_cliente TEXT,               -- ultimo messaggio scritto dal cliente (non broadcast)
    msg_cliente        INTEGER,            -- messaggi scritti dal cliente
    msg_stefano        INTEGER,            -- messaggi di Stefano fuori dal broadcast
    foto_cliente       INTEGER,            -- foto e documenti mandati dal cliente
    vocali_cliente     INTEGER,
    domande            INTEGER,            -- domande con risposta scritta entro 72 h
    senza_risposta     INTEGER,            -- domande senza risposta scritta entro 72 h
    minuti_mediani     REAL,               -- tempo di risposta mediano di Stefano
    argomenti          TEXT,               -- JSON {argomento: domande}
    caricato           TEXT
);

CREATE TABLE IF NOT EXISTS whatsapp_domande (
    codice    TEXT NOT NULL,
    data_ora  TEXT,                        -- inizio della domanda, ISO
    domanda   TEXT,                        -- testo del cliente (turno intero, in chiaro)
    risposta  TEXT,                        -- prima risposta scritta di Stefano
    minuti    REAL,
    argomenti TEXT                         -- JSON lista
);

-- Dati tecnici letti dai libretti mandati in chat (prova del 2026-10-31): mai targa, telaio, intestatario.
CREATE TABLE IF NOT EXISTS whatsapp_libretti (
    codice      TEXT NOT NULL,
    data_ora    TEXT,
    marca       TEXT,
    modello     TEXT,
    anno        TEXT,                      -- prima immatricolazione, solo l'anno
    omologazione TEXT,                     -- numero di omologazione / tipo (campo K / D.2)
    pneumatici  TEXT,                      -- misure ammesse dal libretto, separate da " | "
    leggibile   INTEGER,                   -- 1 si', 0 foto illeggibile o non un libretto
    richiesta   TEXT,                      -- cosa chiedeva il cliente attorno alla foto
    risposta    TEXT                       -- cosa ha risposto/proposto Stefano
);

CREATE INDEX IF NOT EXISTS ix_wa_dom_cliente ON whatsapp_domande(codice);
CREATE INDEX IF NOT EXISTS ix_wa_lib_cliente ON whatsapp_libretti(codice);
