-- Apes Nation Football Prediction private membership schema. Paste into your Supabase SQL Editor once.
-- DO NOT add service_role keys to public files. NEVER let users grant themselves VIP.

create table if not exists public.vip_memberships (
    user_id uuid primary key references auth.users(id) on delete cascade,
    status text not null default 'inactive' check (status in ('active','inactive','cancelled','expired')),
    expires_at timestamptz,
    updated_at timestamptz not null default now()
);

-- At most ONE permanently complimentary VIP account. Only the Supabase project
-- administrator/service role may assign or change it. Never trust client email or UI flags.
create table if not exists public.site_owner (
    slot boolean primary key default true check (slot = true),
    user_id uuid not null unique references auth.users(id) on delete cascade,
    updated_at timestamptz not null default now()
);

create table if not exists public.vip_predictions (
    id text primary key,
    fixture_id bigint not null,
    home text not null,
    away text not null,
    league text not null,
    kickoff timestamptz not null,
    market text not null,
    market_type text not null,
    tip text not null,
    confidence integer check (confidence >= 0 and confidence <= 100),
    projected_total numeric,
    reason text,
    status text not null default 'pending' check (status in ('pending','won','lost','void')),
    final_score text,
    research jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create index if not exists vip_predictions_kickoff on public.vip_predictions(kickoff desc);

alter table public.site_owner enable row level security;
alter table public.vip_memberships enable row level security;
alter table public.vip_predictions enable row level security;

-- Remove all default Data API privileges for non-admin roles, including write.
revoke all on public.site_owner from anon, authenticated;
revoke all on public.vip_memberships from anon, authenticated;
revoke all on public.vip_predictions from anon, authenticated;
grant select on public.site_owner to authenticated;
grant select on public.vip_memberships to authenticated;
grant select on public.vip_predictions to authenticated;
grant all on public.site_owner to service_role;
grant all on public.vip_memberships to service_role;
grant all on public.vip_predictions to service_role;

-- Signed-in users may only see whether THEIR account is the sole owner.
-- Neither ordinary members nor the browser can insert/update/delete owners.
drop policy if exists "Owner reads own status" on public.site_owner;
create policy "Owner reads own status"
on public.site_owner for select to authenticated
using (user_id = (select auth.uid()));

-- Users may read their own status but cannot create or change entitlements.
drop policy if exists "User reads own VIP status" on public.vip_memberships;
create policy "User reads own VIP status"
on public.vip_memberships for select to authenticated
using (user_id = (select auth.uid()));

-- Private research is protected IN THE DATABASE, not just hidden in the browser.
drop policy if exists "Only active VIP reads predictions" on public.vip_predictions;
create policy "Only active VIP reads predictions"
on public.vip_predictions for select to authenticated
using (
    exists (select 1 from public.site_owner o
            where o.user_id = (select auth.uid()))
    or exists (
        select 1 from public.vip_memberships m
        where m.user_id = (select auth.uid())
          and m.status = 'active'
          and m.expires_at > now()
    )
);

-- MANUAL TEST AFTER PAYMENT IS INDEPENDENTLY CONFIRMED:
-- Find the member UUID in Supabase > Authentication > Users, then in SQL Editor:
-- insert into public.vip_memberships (user_id, status, expires_at)
-- values ('REPLACE_WITH_VERIFIED_USER_UUID', 'active', now() + interval '1 month')
-- on conflict (user_id) do update
-- set status = excluded.status, expires_at = excluded.expires_at, updated_at = now();
-- IMPORTANT: Never manually activate on the basis of a screenshot of a payment.
-- In a live system, use a verified Payfast webhook and reconcile renewals/refunds/cancellations.

-- OWNER SETUP: First register and confirm YOUR account on the website.
-- In Supabase Dashboard > Authentication > Users, copy YOUR user UUID.
-- Paste the command below in Supabase SQL Editor, replacing the example.
-- This grants ONLY your single account permanent VIP access, independent of payments:
-- insert into public.site_owner (slot, user_id)
-- values (true, 'REPLACE_WITH_YOUR_OWN_SUPABASE_AUTH_USER_UUID')
-- on conflict (slot) do update
-- set user_id = excluded.user_id, updated_at = now();
-- A new owner assignment REPLACES the old owner automatically.
-- Never place an owner assignment query in public JavaScript or allow a browser to execute it.
