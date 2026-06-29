-- BİST Hisse Tarama — Supabase Storage (kalıcı günlük veri dosyası)
-- Amaç: güncellenen DB (cache.sqlite.gz) Streamlit Cloud'un geçici /tmp'sine rağmen
--       container restart'larında korunsun. Public OKUMA, maintainer-only YAZMA.
--
-- ADIM 1: Storage kovasını oluştur.
insert into storage.buckets (id, name, public)
values ('market-data', 'market-data', true)
on conflict (id) do update set public = true;

-- ADIM 2: Maintainer UUID'lerini gir.
--   Supabase > Authentication > Users  → babanın ve kendi hesabının `id` (uuid) değerini
--   aşağıdaki listeye yaz. (Aynı kişi tek uuid ise tek eleman bırak.)
--   ÖRNEK: array['11111111-1111-1111-1111-111111111111','2222...']::uuid[]
--
-- ⚠️ GÜVENLİK: yazma iznini `authenticated` rolüne AÇMA — public kayıt formu olduğu için
--    kayıt olan herkes verinin üzerine çöp yazabilirdi. Yalnız bu UUID'ler yazabilir.

-- Public okuma (boot indirme auth'suz):
drop policy if exists "market-data public read" on storage.objects;
create policy "market-data public read"
  on storage.objects for select
  using (bucket_id = 'market-data');

-- Maintainer ekleme:
drop policy if exists "market-data maintainer insert" on storage.objects;
create policy "market-data maintainer insert"
  on storage.objects for insert
  with check (
    bucket_id = 'market-data'
    and auth.uid() = any (array[
      '<BABA-UUID-BURAYA>',
      '<BARIS-UUID-BURAYA>'
    ]::uuid[])
  );

-- Maintainer güncelleme (x-upsert üzerine yazma):
drop policy if exists "market-data maintainer update" on storage.objects;
create policy "market-data maintainer update"
  on storage.objects for update
  using (
    bucket_id = 'market-data'
    and auth.uid() = any (array[
      '<BABA-UUID-BURAYA>',
      '<BARIS-UUID-BURAYA>'
    ]::uuid[])
  );
