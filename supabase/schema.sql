-- BİST Hisse Tarama — Supabase şeması
-- Supabase proje > SQL Editor'da çalıştırın.

-- Abonelikler (ödeme sağlayıcısından bağımsız tasarım)
create table if not exists public.subscriptions (
  id                      uuid primary key default gen_random_uuid(),
  user_id                 uuid references auth.users not null,
  provider                text,                     -- 'lemonsqueezy' | 'paddle' | 'stripe' | 'iyzico' | null
  provider_customer_id    text,
  provider_subscription_id text unique,
  plan                    text not null default 'free',    -- 'free' | 'basic' | 'premium' | 'studio' (3 katmanlı, 2026-07-01)
  status                  text not null default 'active',  -- 'active' | 'past_due' | 'canceled' | 'paused'
  current_period_end      timestamptz,
  created_at              timestamptz default now(),
  updated_at              timestamptz default now()
);
alter table public.subscriptions enable row level security;
-- ⚠️ SADECE OKUMA: kullanıcı yalnızca kendi aboneliğini GÖREBİLİR, YAZAMAZ.
-- Insert/update/delete politikası BİLEREK yok → aboneliği yalnızca service_role
-- (ödeme webhook'u) yazar. 'for all' verilirse (WITH CHECK = USING kopyalanır)
-- kayıt olan herkes kendine plan='pro' satırı ekleyip paywall'u aşardı.
create policy "user reads own subscription"
  on public.subscriptions for select
  using (auth.uid() = user_id);

-- Ödeme webhook günlüğü (idempotency + audit)
create table if not exists public.webhook_events (
  id          bigserial primary key,
  provider    text not null default 'lemonsqueezy',
  event_name  text not null,
  event_hash  text not null unique,   -- sha256(ham body) — aynı teslimat tekrar gelirse constraint çakışır, event atlanır
  payload     jsonb not null,
  received_at timestamptz default now()
);
alter table public.webhook_events enable row level security;
-- ⚠️ BİLEREK HİÇBİR POLİCY YOK: subscriptions'daki aynı desen — anon/authenticated
-- hiçbir şey okuyup yazamaz, yalnızca service_role (Edge Function) erişir.

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

-- Akıllı Radar (2026-07-02, G1 güvenlik düzeltmesi) — ücretli radar/sonuç verisi
-- artık burada, tier-RLS ile korunuyor; public Storage gzip'inde ARTIK DURMUYOR.
create or replace function public.has_paid_tier()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.subscriptions s
    where s.user_id = auth.uid()
      and s.plan in ('basic','premium','studio')
      and s.status in ('active','past_due')      -- past_due: ödeme gecikmesi tolerans penceresi
      and (s.current_period_end is null or s.current_period_end > now())
  );
$$;
revoke all on function public.has_paid_tier() from public;
grant execute on function public.has_paid_tier() to authenticated;

create table if not exists public.radar_snapshots (
  data_date     date not null,
  symbol        text not null,
  model_kind    text not null default 'absolute',
  radar_status  text,
  ml_score      real, score_5 real, score_10 real, relative_score real,
  confidence    text, data_confidence text, liquidity_label text,
  trend_label   text, volume_label text, horizon text,
  simple_reason text, main_risk text,
  son           real, fark real,
  created_at    timestamptz default now(),
  primary key (data_date, symbol, model_kind)
);
alter table public.radar_snapshots enable row level security;
create policy "paid tier reads radar" on public.radar_snapshots
  for select to authenticated
  using ( (select public.has_paid_tier()) );
-- INSERT/UPDATE/DELETE policy BİLEREK YOK → yalnız service_role (VPS cron) yazar.

create table if not exists public.radar_outcomes (
  signal_date     date not null,
  symbol          text not null,
  model_kind      text not null,
  radar_status    text,
  ml_score        real, score_5 real, score_10 real, relative_score real,
  confidence      text, signal_horizon text, simple_reason text, main_risk text,
  horizon_days    integer not null,
  start_price     real, end_date date, end_price real,
  abs_return      real, max_return real, min_return real,
  success         integer,
  evaluated_at    timestamptz default now(),
  primary key (signal_date, symbol, model_kind, horizon_days)
);
alter table public.radar_outcomes enable row level security;
create policy "paid tier reads radar outcomes" on public.radar_outcomes
  for select to authenticated
  using ( (select public.has_paid_tier()) );
-- INSERT/UPDATE/DELETE policy BİLEREK YOK → yalnız service_role (VPS cron) yazar.

-- Streamlit secrets için gerekli anahtar adları:
--   SUPABASE_URL      = https://<proje-id>.supabase.co
--   SUPABASE_ANON_KEY = <Project Settings > API > anon public>
