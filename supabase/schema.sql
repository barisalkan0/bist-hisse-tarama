-- BİST Hisse Tarama — Supabase şeması
-- Supabase proje > SQL Editor'da çalıştırın.

-- Abonelikler (ödeme sağlayıcısından bağımsız tasarım)
create table if not exists public.subscriptions (
  id                      uuid primary key default gen_random_uuid(),
  user_id                 uuid references auth.users not null,
  provider                text,                     -- 'paddle' | 'stripe' | 'iyzico' | null
  provider_customer_id    text,
  provider_subscription_id text unique,
  plan                    text not null default 'free',    -- 'free' | 'pro'
  status                  text not null default 'active',  -- 'active' | 'past_due' | 'canceled' | 'paused'
  current_period_end      timestamptz,
  created_at              timestamptz default now(),
  updated_at              timestamptz default now()
);
alter table public.subscriptions enable row level security;
create policy "user owns subscription"
  on public.subscriptions for all
  using (auth.uid() = user_id);

-- Notlar
create table if not exists public.notes (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid references auth.users not null,
  symbol     text not null,
  note_text  text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique (user_id, symbol)
);
alter table public.notes enable row level security;
create policy "user owns notes"
  on public.notes for all
  using (auth.uid() = user_id);

-- Favoriler
create table if not exists public.favorites (
  user_id uuid references auth.users not null,
  symbol  text not null,
  primary key (user_id, symbol)
);
alter table public.favorites enable row level security;
create policy "user owns favorites"
  on public.favorites for all
  using (auth.uid() = user_id);

-- Gizleme listesi (kara liste)
create table if not exists public.blacklist (
  user_id uuid references auth.users not null,
  symbol  text not null,
  primary key (user_id, symbol)
);
alter table public.blacklist enable row level security;
create policy "user owns blacklist"
  on public.blacklist for all
  using (auth.uid() = user_id);

-- Streamlit secrets için gerekli anahtar adları:
--   SUPABASE_URL      = https://<proje-id>.supabase.co
--   SUPABASE_ANON_KEY = <Project Settings > API > anon public>
