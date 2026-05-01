-- PostgreSQL schema for Biopharma Agent analysis storage.
-- Apply with:
--   psql "$BIOPHARMA_POSTGRES_DSN" -f infra/postgres/schema.sql

create table if not exists sources (
    name text primary key,
    kind text not null,
    url text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists documents (
    id bigserial primary key,
    document_id text not null,
    source_name text not null references sources(name) on update cascade,
    checksum text not null,
    title text,
    url text,
    language text,
    published_at timestamptz,
    collected_at timestamptz,
    raw_uri text,
    text text not null default '',
    metadata jsonb not null default '{}'::jsonb,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_name, document_id)
);

create index if not exists documents_source_created_idx on documents(source_name, created_at desc);
create index if not exists documents_checksum_idx on documents(checksum);
create index if not exists documents_url_idx on documents(url);

create table if not exists insights (
    id bigserial primary key,
    source_name text not null,
    document_id text not null,
    provider text not null,
    model text not null,
    summary text not null default '',
    event_type text not null default '',
    risk text not null default '',
    needs_human_review boolean not null default false,
    payload jsonb not null default '{}'::jsonb,
    pipeline_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_name, document_id, provider, model),
    foreign key (source_name, document_id)
        references documents(source_name, document_id)
        on update cascade
        on delete cascade
);

create index if not exists insights_source_created_idx on insights(source_name, created_at desc);
create index if not exists insights_event_type_idx on insights(event_type);
create index if not exists insights_risk_idx on insights(risk);
create index if not exists insights_review_idx on insights(needs_human_review);

create table if not exists insight_entities (
    id bigserial primary key,
    insight_id bigint not null references insights(id) on delete cascade,
    name text not null,
    normalized_name text,
    entity_type text,
    confidence numeric,
    evidence text,
    payload jsonb not null default '{}'::jsonb
);

create index if not exists insight_entities_name_idx on insight_entities(normalized_name);
create index if not exists insight_entities_type_idx on insight_entities(entity_type);

create table if not exists insight_events (
    id bigserial primary key,
    insight_id bigint not null references insights(id) on delete cascade,
    event_type text,
    title text,
    event_date text,
    companies text[] not null default '{}',
    amount text,
    stage text,
    confidence numeric,
    evidence text,
    payload jsonb not null default '{}'::jsonb
);

create index if not exists insight_events_type_idx on insight_events(event_type);
create index if not exists insight_events_companies_idx on insight_events using gin(companies);

create table if not exists insight_relations (
    id bigserial primary key,
    insight_id bigint not null references insights(id) on delete cascade,
    subject text not null,
    predicate text not null,
    object text not null,
    confidence numeric,
    evidence text,
    payload jsonb not null default '{}'::jsonb
);

create index if not exists insight_relations_subject_idx on insight_relations(subject);
create index if not exists insight_relations_object_idx on insight_relations(object);

create table if not exists risk_signals (
    id bigserial primary key,
    insight_id bigint not null references insights(id) on delete cascade,
    risk_type text,
    severity text,
    rationale text,
    evidence text,
    payload jsonb not null default '{}'::jsonb
);

create index if not exists risk_signals_severity_idx on risk_signals(severity);
create index if not exists risk_signals_type_idx on risk_signals(risk_type);

create table if not exists feedback (
    id bigserial primary key,
    document_id text not null,
    reviewer text not null,
    decision text not null check (decision in ('accept', 'reject', 'correct')),
    comment text not null default '',
    corrections jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists feedback_document_idx on feedback(document_id, created_at desc);

create table if not exists source_states (
    source_name text primary key,
    kind text not null default '',
    collector text not null default 'feed',
    category text not null default '',
    enabled boolean not null default true,
    last_status text not null default 'never_run',
    last_started_at timestamptz,
    last_completed_at timestamptz,
    last_error text not null default '',
    last_fetched integer not null default 0,
    last_selected integer not null default 0,
    last_analyzed integer not null default 0,
    last_skipped_seen integer not null default 0,
    last_document_ids text[] not null default '{}',
    seen_document_ids text[] not null default '{}',
    consecutive_failures integer not null default 0,
    payload jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create index if not exists source_states_status_idx on source_states(last_status, updated_at desc);
