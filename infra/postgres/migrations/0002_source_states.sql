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
