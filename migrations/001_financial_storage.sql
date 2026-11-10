CREATE TABLE companies (
    cik text PRIMARY KEY CHECK (cik ~ '^[0-9]{10}$'),
    ticker text NOT NULL,
    name text NOT NULL
);
CREATE TABLE snapshots (
    snapshot_id text PRIMARY KEY CHECK (snapshot_id ~ '^[0-9a-f]{64}$'),
    cik text NOT NULL REFERENCES companies(cik),
    source_url text NOT NULL,
    local_path text NOT NULL,
    UNIQUE (snapshot_id, cik)
);
CREATE TABLE filings (
    cik text NOT NULL REFERENCES companies(cik),
    accession text NOT NULL CHECK (accession ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'),
    filed date NOT NULL,
    form text NOT NULL CHECK (form IN ('10-K','10-K/A','10-Q','10-Q/A')),
    source_url text NOT NULL,
    PRIMARY KEY (cik, accession)
);
CREATE TABLE financial_facts (
    fact_id text PRIMARY KEY CHECK (fact_id ~ '^[0-9a-f]{64}$'),
    cik text NOT NULL,
    accession text NOT NULL,
    metric text NOT NULL,
    taxonomy text NOT NULL,
    tag text NOT NULL,
    unit text NOT NULL CHECK (unit = 'USD'),
    value numeric NOT NULL CHECK (value NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    start_date date,
    end_date date NOT NULL,
    period_kind text NOT NULL,
    filing_fy integer,
    filing_fp text,
    frame text,
    FOREIGN KEY (cik, accession) REFERENCES filings(cik, accession),
    CHECK (start_date IS NULL OR start_date <= end_date),
    UNIQUE (fact_id, cik)
);
CREATE INDEX facts_company_metric_period ON financial_facts(cik, metric, end_date, start_date);
CREATE TABLE datasets (
    dataset_id text PRIMARY KEY CHECK (dataset_id ~ '^[0-9a-f]{64}$'),
    source_name text NOT NULL,
    start_date date NOT NULL,
    as_of date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (start_date <= as_of)
);
CREATE TABLE dataset_companies (
    dataset_id text NOT NULL REFERENCES datasets(dataset_id),
    cik text NOT NULL REFERENCES companies(cik),
    snapshot_id text NOT NULL,
    retrieved_at timestamptz NOT NULL,
    coverage jsonb NOT NULL,
    pipeline_identity jsonb NOT NULL,
    selection_policy text NOT NULL,
    period_policy text NOT NULL,
    PRIMARY KEY (dataset_id, cik),
    FOREIGN KEY (snapshot_id, cik) REFERENCES snapshots(snapshot_id, cik)
);
CREATE TABLE dataset_facts (
    dataset_id text NOT NULL,
    cik text NOT NULL,
    fact_id text NOT NULL,
    PRIMARY KEY (dataset_id, cik, fact_id),
    FOREIGN KEY (dataset_id, cik) REFERENCES dataset_companies(dataset_id, cik),
    FOREIGN KEY (fact_id, cik) REFERENCES financial_facts(fact_id, cik)
);
CREATE TABLE observations (
    dataset_id text NOT NULL,
    observation_id text NOT NULL,
    cik text NOT NULL,
    metric text NOT NULL,
    start_date date,
    end_date date NOT NULL,
    unit text NOT NULL CHECK (unit = 'USD'),
    period_kind text NOT NULL,
    status text NOT NULL CHECK (status IN ('selected','ambiguous','unsupported_period')),
    selected_fact_id text,
    candidate_count integer NOT NULL CHECK (candidate_count > 0),
    PRIMARY KEY (dataset_id, observation_id),
    FOREIGN KEY (dataset_id, cik) REFERENCES dataset_companies(dataset_id, cik),
    FOREIGN KEY (dataset_id, cik, selected_fact_id) REFERENCES dataset_facts(dataset_id, cik, fact_id),
    CHECK ((status = 'selected') = (selected_fact_id IS NOT NULL)),
    CHECK (start_date IS NULL OR start_date <= end_date)
);
CREATE TABLE ingestion_runs (
    run_id uuid PRIMARY KEY,
    dataset_id text REFERENCES datasets(dataset_id),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running','success','failed')),
    error_kind text,
    summary jsonb
);
CREATE VIEW latest_company_datasets AS
SELECT DISTINCT ON (dc.cik) dc.cik, dc.dataset_id
FROM dataset_companies dc JOIN datasets d USING (dataset_id)
ORDER BY dc.cik, d.as_of DESC, dc.retrieved_at DESC, d.created_at DESC, d.dataset_id;
CREATE VIEW current_financial_facts AS
SELECT c.cik, c.ticker, c.name, o.metric, f.value, o.unit, o.start_date, o.end_date,
       o.period_kind, f.taxonomy, f.tag, f.accession, fi.filed, fi.form, fi.source_url,
       o.dataset_id, dc.snapshot_id, d.as_of, dc.coverage
FROM latest_company_datasets latest
JOIN dataset_companies dc ON (dc.cik, dc.dataset_id) = (latest.cik, latest.dataset_id)
JOIN datasets d ON d.dataset_id = dc.dataset_id
JOIN observations o ON (o.cik, o.dataset_id) = (dc.cik, dc.dataset_id)
JOIN financial_facts f ON f.fact_id = o.selected_fact_id
JOIN filings fi ON (fi.cik, fi.accession) = (f.cik, f.accession)
JOIN companies c ON c.cik = o.cik
WHERE o.status = 'selected';
