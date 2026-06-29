-- BİST Hisse Tarama — Supabase Storage (kalıcı günlük veri dosyası)
-- Amaç: VPS cron'u güncel DB'yi (cache.sqlite.gz) bu kovaya yazar; uygulama açılışta indirir.
-- Public OKUMA (uygulama auth'suz indirir), YAZMA yalnız "robot" maintainer hesabına.
--
-- ÖN KOŞUL: 'market-data' kovası Supabase > Storage'da Public olarak oluşturulmuş olmalı.
-- (Public kova -> okuma public URL ile auth'suz çalışır; aşağıda sadece YAZMA izni veriyoruz.)
--
-- Robot hesabı uuid: cec0e3de-7023-4658-a7b3-9c9d87b322be (robot@barislkn.com)
-- ⚠️ Yazma iznini 'authenticated' rolüne AÇMA — public kayıt var; kayıt olan herkes ezerdi.

drop policy if exists "market-data robot insert" on storage.objects;
create policy "market-data robot insert"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'market-data'
    and auth.uid() = 'cec0e3de-7023-4658-a7b3-9c9d87b322be'::uuid
  );

drop policy if exists "market-data robot update" on storage.objects;
create policy "market-data robot update"
  on storage.objects for update to authenticated
  using (
    bucket_id = 'market-data'
    and auth.uid() = 'cec0e3de-7023-4658-a7b3-9c9d87b322be'::uuid
  );
