-- Lode schema. Rebuilt by every monthly load (see src/lode/etl/load.py).

create table if not exists company (
    cnpj_basico          char(8) primary key,
    legal_name           text not null,
    legal_nature         char(4) not null,
    capital              numeric(16, 2) not null,
    size_code            char(2) not null,     -- 00 not informed, 01 micro, 03 small, 05 other
    is_simples           boolean not null,
    simples_since        date,
    is_mei               boolean not null,
    mei_since            date,
    partners             smallint not null,    -- counts only: no partner names are stored (LGPD)
    partners_person      smallint not null,
    partners_company     smallint not null,
    partners_foreign     smallint not null,
    youngest_age_band    smallint,             -- Receita bands: 1 = 0-12 ... 9 = over 80
    oldest_age_band      smallint,
    first_partner_since  date
);

create table if not exists establishment (
    cnpj               char(14) primary key,
    cnpj_basico        char(8) not null references company,
    is_headquarters    boolean not null,
    trade_name         text,
    opened_on          date,
    cnae_main          char(7) not null,
    cnaes_secondary    char(7)[] not null,
    street             text,
    district           text,
    zip_code           char(8),
    uf                 char(2) not null,
    municipality_code  char(4) not null,
    phone1             text,
    phone2             text,
    email              text
);
create index if not exists establishment_company on establishment (cnpj_basico);
create index if not exists establishment_place on establishment (uf, municipality_code);

create table if not exists municipality (
    code  char(4) primary key,
    name  text not null
);

create table if not exists cnae (
    code         char(7) primary key,
    description  text not null
);

create table if not exists load_info (
    id              boolean primary key default true check (id),  -- single row
    month           text not null,
    loaded_at       timestamptz not null default now(),
    companies       integer not null,
    establishments  integer not null,
    rows_read       jsonb not null
);

-- Public contracts (PNCP) won by our companies. No foreign key to company on purpose: the
-- monthly Receita reload recreates company, and contracts take hours to download.
create table if not exists public_contract (
    id             text primary key,         -- numeroControlePNCP
    cnpj           char(14) not null,        -- supplier establishment
    cnpj_basico    char(8) not null,
    object         text,
    value          numeric(18, 2),
    signed_on      date,
    valid_from     date,
    valid_to       date,
    published_at   timestamp,
    contract_type  text,
    category       text,
    buyer_cnpj     char(14),
    buyer_name     text,
    buyer_sphere   char(1),                  -- F federal, E state, M municipal, D district
    buyer_uf       char(2),
    buyer_ibge     char(7)
);
create index if not exists public_contract_company on public_contract (cnpj_basico);

create table if not exists pncp_info (
    id               boolean primary key default true check (id),
    period_start     date not null,
    period_end       date not null,
    loaded_at        timestamptz not null default now(),
    contracts_read   integer not null,
    contracts_kept   integer not null
);

-- Score of every company, computed at load time by `python -m lode.model score`. The API only
-- reads this table, so it never needs the model file.
create table if not exists company_score (
    cnpj_basico  char(8) primary key,
    score        double precision not null,  -- probability of winning a public contract
    rank         integer not null,           -- 1 = highest score
    reasons      jsonb                       -- log-odds contribution of each feature vs the
                                             -- average company (logistic models only)
);
-- What the API lists, copied at scoring time so requests need no per-company aggregation: the
-- headquarters, or (when the headquarters is in another state) the oldest establishment we have.
alter table company_score add column if not exists trade_name text;
alter table company_score add column if not exists municipality_code char(4);
create index if not exists company_score_rank on company_score (rank);
create index if not exists company_score_place on company_score (municipality_code, rank);

create table if not exists score_info (
    id             boolean primary key default true check (id),  -- single row
    cutoff         date not null,
    model_version  text not null,
    model          text not null,
    scored_at      timestamptz not null default now(),
    companies      integer not null,
    metrics        jsonb not null           -- holdout evaluation of the model
);

-- Name search ("totvs" anywhere in the name) with trigram indexes: a plain ilike '%...%' reads
-- every row.
create extension if not exists pg_trgm;
create index if not exists company_name_search on company using gin (legal_name gin_trgm_ops);
create index if not exists company_score_name_search
    on company_score using gin (trade_name gin_trgm_ops);
