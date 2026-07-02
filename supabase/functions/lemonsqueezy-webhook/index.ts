// Lemon Squeezy abonelik webhook alıcısı.
//
// İmza doğrular (X-Signature, HMAC-SHA256, HAM body üzerinden — JSON.parse
// SONRASI değil), aynı event'i idempotent şekilde işler (webhook_events.event_hash
// UNIQUE), ve subscriptions tablosunu service_role ile günceller.
//
// Deploy: `supabase functions deploy lemonsqueezy-webhook --no-verify-jwt`
// (Lemon Squeezy Supabase JWT göndermediği için JWT doğrulaması kapatılmalı.)
// Secrets (`supabase secrets set KEY=value ...`):
//   LEMONSQUEEZY_WEBHOOK_SECRET               — Lemon Squeezy'nin verdiği signing secret
//   LEMONSQUEEZY_VARIANT_ID_BASIC_MONTHLY/YEARLY
//   LEMONSQUEEZY_VARIANT_ID_PREMIUM_MONTHLY/YEARLY
//   LEMONSQUEEZY_VARIANT_ID_STUDIO_MONTHLY/YEARLY   — 3 katman × aylık/yıllık = 6 varyant ID'si
// SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY Edge Function ortamına Supabase
// tarafından otomatik enjekte edilir — elle ayarlamaya gerek yok.
//
// Test: Lemon Squeezy Dashboard → Webhooks → ilgili webhook → "Simulate event"
// ile 8 desteklenen event tek tek tetiklenebilir. Loglar:
//   supabase functions logs lemonsqueezy-webhook

import { createClient } from "npm:@supabase/supabase-js@2";

const WEBHOOK_SECRET = Deno.env.get("LEMONSQUEEZY_WEBHOOK_SECRET") ?? "";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { persistSession: false },
});

// variant_id -> tier ('basic' | 'premium' | 'studio'). Her tier'ın aylık VE
// yıllık varyantı aynı tier'a map'lenir (dönem uzunluğu ayrıca renews_at'ten
// gelir, tier için ayrı bir alan gerekmez). Env'de olmayan varyantlar haritaya
// girmez (henüz oluşturulmamış olabilirler).
const VARIANT_TIER_ENV_KEYS: Array<[string, string]> = [
  ["basic", "LEMONSQUEEZY_VARIANT_ID_BASIC_MONTHLY"],
  ["basic", "LEMONSQUEEZY_VARIANT_ID_BASIC_YEARLY"],
  ["premium", "LEMONSQUEEZY_VARIANT_ID_PREMIUM_MONTHLY"],
  ["premium", "LEMONSQUEEZY_VARIANT_ID_PREMIUM_YEARLY"],
  ["studio", "LEMONSQUEEZY_VARIANT_ID_STUDIO_MONTHLY"],
  ["studio", "LEMONSQUEEZY_VARIANT_ID_STUDIO_YEARLY"],
];
const VARIANT_TIER_MAP: Record<string, string> = {};
for (const [tier, envKey] of VARIANT_TIER_ENV_KEYS) {
  const variantId = Deno.env.get(envKey);
  if (variantId) VARIANT_TIER_MAP[variantId] = tier;
}

function tierForVariant(variantId: string | undefined): string | null {
  if (!variantId) return null;
  return VARIANT_TIER_MAP[variantId] ?? null;
}

// Kullanıcının onayladığı 8 event — bunun dışındaki her şey sadece loglanır,
// subscriptions'a dokunulmaz.
const SUPPORTED_EVENTS = new Set([
  "subscription_created",
  "subscription_updated",
  "subscription_cancelled",
  "subscription_expired",
  "subscription_paused",
  "subscription_unpaused",
  "subscription_payment_success",
  "subscription_payment_failed",
]);

function log(...args: unknown[]) {
  console.log("[lemonsqueezy-webhook]", ...args);
}
function warn(...args: unknown[]) {
  console.warn("[lemonsqueezy-webhook]", ...args);
}
function err(...args: unknown[]) {
  console.error("[lemonsqueezy-webhook]", ...args);
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmacSha256Hex(secret: string, bytes: Uint8Array): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = await crypto.subtle.sign("HMAC", key, bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(a: string, b: string): boolean {
  const aBytes = new TextEncoder().encode(a);
  const bBytes = new TextEncoder().encode(b);
  if (aBytes.length !== bBytes.length) return false;
  let diff = 0;
  for (let i = 0; i < aBytes.length; i++) diff |= aBytes[i] ^ bBytes[i];
  return diff === 0;
}

// event_name -> subscriptions.status. `subscription_cancelled` BİLEREK 'active'
// döner: Lemon Squeezy'de "cancelled" dönem sonuna (ends_at) kadar hâlâ geçerli
// demektir; mevcut is_pro() zaten current_period_end > now() kontrolü yaptığı
// için kullanıcı süre dolana kadar otomatik Pro kalır, ekstra kod gerekmez.
function statusForEvent(eventName: string, attrs: Record<string, unknown>): string {
  switch (eventName) {
    case "subscription_created":
    case "subscription_unpaused":
    case "subscription_payment_success":
    case "subscription_cancelled":
      return "active";
    case "subscription_paused":
      return "paused";
    case "subscription_payment_failed":
      return "past_due";
    case "subscription_expired":
      return "canceled";
    case "subscription_updated": {
      // "updated" farklı sebeplerle tetiklenebilir (plan değişikliği, ödeme
      // durumu vb.) — Lemon Squeezy'nin kendi anlık durumunu esas alırız.
      switch (attrs.status) {
        case "paused":
          return "paused";
        case "past_due":
        case "unpaid":
          return "past_due";
        case "expired":
          return "canceled";
        default:
          return "active"; // on_trial, active, cancelled (hâlâ geçerli)
      }
    }
    default:
      return "active";
  }
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("method not allowed", { status: 405 });
  }
  if (!WEBHOOK_SECRET) {
    err("LEMONSQUEEZY_WEBHOOK_SECRET ayarlanmamış — `supabase secrets set` ile ekleyin.");
    return new Response("webhook not configured", { status: 500 });
  }

  const rawBody = new Uint8Array(await req.arrayBuffer());
  const signature = req.headers.get("X-Signature") ?? "";
  const expected = await hmacSha256Hex(WEBHOOK_SECRET, rawBody);
  if (!signature || !timingSafeEqual(expected, signature)) {
    warn("Geçersiz imza, istek reddedildi.");
    return new Response("invalid signature", { status: 401 });
  }

  // deno-lint-ignore no-explicit-any
  let payload: any;
  try {
    payload = JSON.parse(new TextDecoder().decode(rawBody));
  } catch {
    warn("Body geçerli JSON değil.");
    return new Response("invalid json", { status: 400 });
  }

  const eventName: string = payload?.meta?.event_name ?? req.headers.get("X-Event-Name") ?? "unknown";
  const eventHash = await sha256Hex(rawBody);
  const testMode = Boolean(payload?.meta?.test_mode);

  log(`event=${eventName} test_mode=${testMode} hash=${eventHash.slice(0, 12)}…`);

  // Idempotency + audit log: aynı event_hash daha önce işlendiyse unique-violation alınır.
  const { error: insertErr } = await supabase.from("webhook_events").insert({
    provider: "lemonsqueezy",
    event_name: eventName,
    event_hash: eventHash,
    payload,
  });
  if (insertErr) {
    if (insertErr.code === "23505") {
      log("Bu event daha önce işlenmiş (event_hash tekrarı), atlanıyor.");
      return new Response("ok (duplicate)", { status: 200 });
    }
    err("webhook_events insert hatası:", insertErr.message);
    // Log tablosuna yazamasak da abonelik güncellemesini denemeye devam ederiz.
  }

  if (!SUPPORTED_EVENTS.has(eventName)) {
    log(`Desteklenmeyen event (${eventName}) — sadece loglandı, subscriptions'a dokunulmadı.`);
    return new Response("ok (unhandled event)", { status: 200 });
  }

  const attrs = payload?.data?.attributes ?? {};
  const userId: string | undefined = payload?.meta?.custom_data?.user_id;
  const providerSubscriptionId: string | undefined = payload?.data?.id;

  if (!providerSubscriptionId) {
    warn("payload.data.id yok, abonelik güncellenemedi.");
    return new Response("ok (missing subscription id)", { status: 200 });
  }

  const status = statusForEvent(eventName, attrs);
  const currentPeriodEnd =
    eventName === "subscription_cancelled" || eventName === "subscription_expired"
      ? (attrs.ends_at ?? attrs.renews_at ?? null)
      : (attrs.renews_at ?? null);

  // `expired` her zaman 'free'e düşer (hangi varyant olduğu önemsiz). Diğer
  // tüm event'lerde variant_id -> tier eşlemesi zorunlu; eşleşmezse (env'de
  // henüz tanımlanmamış bir varyant) yanlış tier yazmamak için işlem atlanır.
  const variantId = attrs.variant_id != null ? String(attrs.variant_id) : undefined;
  let plan: string;
  if (eventName === "subscription_expired") {
    plan = "free";
  } else {
    const tier = tierForVariant(variantId);
    if (!tier) {
      warn(
        `variant_id=${variantId ?? "(yok)"} bilinen bir tier'a eşlenemedi ` +
          `(subscription=${providerSubscriptionId}) — LEMONSQUEEZY_VARIANT_ID_* secret'ları eksik/yanlış olabilir. ` +
          `subscriptions güncellenmedi, ham payload webhook_events'te duruyor.`,
      );
      return new Response("ok (unknown variant, see logs)", { status: 200 });
    }
    plan = tier;
  }

  const row: Record<string, unknown> = {
    provider: "lemonsqueezy",
    provider_subscription_id: providerSubscriptionId,
    provider_customer_id: attrs.customer_id != null ? String(attrs.customer_id) : null,
    plan,
    status,
    current_period_end: currentPeriodEnd,
    updated_at: new Date().toISOString(),
  };
  if (userId) {
    row.user_id = userId;
  } else {
    // custom_data eksikse: var olan satır varsa (user_id zaten kayıtlı) sadece
    // diğer alanlar güncellenir. Bu subscription hiç görülmediyse (ilk event)
    // user_id NOT NULL olduğu için insert başarısız olur — aşağıda loglanır.
    warn(`custom_data.user_id yok (subscription=${providerSubscriptionId}).`);
  }

  const { error: upsertErr } = await supabase
    .from("subscriptions")
    .upsert(row, { onConflict: "provider_subscription_id" });

  if (upsertErr) {
    err(`subscriptions upsert hatası (subscription=${providerSubscriptionId}):`, upsertErr.message);
    if (!userId) {
      err("Muhtemel sebep: custom_data.user_id eksik ve bu yeni bir abonelik — manuel eşleme gerekebilir (ham payload webhook_events tablosunda duruyor).");
    }
    // G5 güvenlik düzeltmesi: idempotency kaydını geri al ve 500 dön. Aksi
    // halde bu satır webhook_events'te dururken Lemon Squeezy retry'ı
    // event_hash unique constraint'ine takılıp "duplicate" sanılıp atlanır ve
    // başarısız abonelik güncellemesi sessizce kaybolurdu.
    const { error: deleteErr } = await supabase
      .from("webhook_events")
      .delete()
      .eq("event_hash", eventHash);
    if (deleteErr) {
      err("webhook_events geri alma hatası (idempotency kaydı kalmış olabilir):", deleteErr.message);
    }
    return new Response("subscription update failed, retry", { status: 500 });
  }

  log(`subscriptions güncellendi: subscription=${providerSubscriptionId} plan=${plan} status=${status} user=${userId ?? "(değişmedi)"}`);
  return new Response("ok", { status: 200 });
});
