-- ============================================
-- OshiPay DB セットアップ（完全版・冪等）
-- 何度実行しても安全
-- ============================================

-- ========================================
-- 1. テーブル作成
-- ========================================
CREATE TABLE IF NOT EXISTS public.supports (
    id           BIGSERIAL    PRIMARY KEY,
    support_id   UUID         UNIQUE NOT NULL,
    creator_acct TEXT         NOT NULL,
    creator_name TEXT         NOT NULL,
    amount       INTEGER      NOT NULL,
    message      TEXT         DEFAULT '',
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    reply_emoji  TEXT,
    reply_text   TEXT,
    replied_at   TIMESTAMPTZ,
    owner_id     TEXT,
    is_listed    BOOLEAN      DEFAULT FALSE,
    list_price   INTEGER
);

CREATE TABLE IF NOT EXISTS public.creators (
    acct_id       TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.supporters (
    supporter_id  TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.deleted_slugs (
    slug        TEXT PRIMARY KEY,
    acct_id     TEXT NOT NULL,
    deleted_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.stamps (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    creator_acct TEXT NOT NULL,
    stamp_type   TEXT NOT NULL,
    device_hash  TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (creator_acct, device_hash)
);

CREATE TABLE IF NOT EXISTS public.pending_supports (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    creator_acct    TEXT NOT NULL,
    amount          INTEGER NOT NULL DEFAULT 0,
    message         TEXT,
    contact_info    TEXT,
    supporter_email TEXT,
    supporter_id    TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    expires_at      TIMESTAMPTZ DEFAULT (now() + interval '72 hours'),
    status          TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS public.supporter_accounts (
    supporter_id       TEXT PRIMARY KEY DEFAULT ('sup_' || substr(gen_random_uuid()::text, 1, 16)),
    email              TEXT UNIQUE NOT NULL,
    password_hash      TEXT,
    stripe_customer_id TEXT,
    created_at         TIMESTAMPTZ DEFAULT now()
);
-- password_hash は既存テーブルでも NOT NULL を外す（冪等）
ALTER TABLE public.supporter_accounts ALTER COLUMN password_hash DROP NOT NULL;

-- ========================================
-- 2. カラム追加（supports）
-- ========================================
ALTER TABLE public.supports ADD COLUMN IF NOT EXISTS supporter_id  TEXT;
ALTER TABLE public.supports ADD COLUMN IF NOT EXISTS creator_rank  INTEGER;

-- ========================================
-- 3. カラム追加（supporters）
-- ========================================
ALTER TABLE public.supporters ALTER COLUMN display_name DROP NOT NULL;
ALTER TABLE public.supporters ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE public.supporters ADD COLUMN IF NOT EXISTS email         TEXT;

-- ========================================
-- 4. カラム追加（creators）
-- ========================================
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS name           TEXT;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS display_name   TEXT;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS slug           TEXT UNIQUE;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS bio            TEXT DEFAULT '';
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS genre          TEXT DEFAULT '';
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS photo_url      TEXT DEFAULT '';
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS sns_links      JSONB DEFAULT '{}';
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS x_url          TEXT;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS instagram_url  TEXT;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS tiktok_url     TEXT;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS qr_url         TEXT;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS is_deleted     BOOLEAN DEFAULT FALSE;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS profile_done   BOOLEAN DEFAULT FALSE;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS email          TEXT;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS stripe_acct_id TEXT;
ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS payout_enabled BOOLEAN DEFAULT FALSE;

-- ========================================
-- 5. インデックス
-- ========================================
ALTER TABLE public.pending_supports ADD COLUMN IF NOT EXISTS reminded_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_supports_supporter_id ON public.supports(supporter_id);
CREATE INDEX IF NOT EXISTS idx_creators_slug         ON public.creators(slug);
CREATE INDEX IF NOT EXISTS idx_creators_is_deleted   ON public.creators(is_deleted);

-- ========================================
-- 6. RLS 有効化
-- ========================================
ALTER TABLE public.supports           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.creators           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.supporters         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.deleted_slugs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stamps             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pending_supports   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.supporter_accounts ENABLE ROW LEVEL SECURITY;

-- ========================================
-- 7. RLS ポリシー（全部 DROP → CREATE）
-- ========================================
DROP POLICY IF EXISTS "anon can read creators"                ON public.creators;
DROP POLICY IF EXISTS "anon can read supports"                ON public.supports;
DROP POLICY IF EXISTS "Public can read stamps"                ON public.stamps;
DROP POLICY IF EXISTS "Public can insert stamps"              ON public.stamps;
DROP POLICY IF EXISTS "Public insert pending_supports"        ON public.pending_supports;
DROP POLICY IF EXISTS "Public select pending_supports"        ON public.pending_supports;
DROP POLICY IF EXISTS "Public can insert supporter_accounts"  ON public.supporter_accounts;
DROP POLICY IF EXISTS "Public can read supporter_accounts"    ON public.supporter_accounts;
DROP POLICY IF EXISTS "Public can update supporter_accounts"  ON public.supporter_accounts;

CREATE POLICY "anon can read creators"               ON public.creators           FOR SELECT TO anon USING (true);
CREATE POLICY "anon can read supports"               ON public.supports           FOR SELECT TO anon USING (true);
CREATE POLICY "Public can read stamps"               ON public.stamps             FOR SELECT         USING (true);
CREATE POLICY "Public can insert stamps"             ON public.stamps             FOR INSERT         WITH CHECK (true);
CREATE POLICY "Public insert pending_supports"       ON public.pending_supports   FOR INSERT         WITH CHECK (true);
CREATE POLICY "Public select pending_supports"       ON public.pending_supports   FOR SELECT         USING (true);
CREATE POLICY "Public can insert supporter_accounts" ON public.supporter_accounts FOR INSERT         WITH CHECK (true);
CREATE POLICY "Public can read supporter_accounts"   ON public.supporter_accounts FOR SELECT         USING (true);
CREATE POLICY "Public can update supporter_accounts" ON public.supporter_accounts FOR UPDATE         USING (true);

-- ========================================
-- 8. Storage ポリシー
-- ========================================
DROP POLICY IF EXISTS "public upload creator-photos" ON storage.objects;
DROP POLICY IF EXISTS "public update creator-photos" ON storage.objects;
DROP POLICY IF EXISTS "public read creator-photos"   ON storage.objects;

CREATE POLICY "public upload creator-photos" ON storage.objects FOR INSERT TO anon WITH CHECK (bucket_id = 'creator-photos');
CREATE POLICY "public update creator-photos" ON storage.objects FOR UPDATE TO anon USING  (bucket_id = 'creator-photos');
CREATE POLICY "public read creator-photos"   ON storage.objects FOR SELECT TO anon USING  (bucket_id = 'creator-photos');

-- ========================================
-- 9. 初期データ
-- ========================================
INSERT INTO public.creators (acct_id, password_hash)
VALUES ('acct_1T6prLJxxP0VtABn', '65b97db1bbe1f74210dfd667cff21455ab298ea12264e87290e33039b10a0ad8')
ON CONFLICT (acct_id) DO NOTHING;

UPDATE public.creators
SET
  name         = 'あさぎり｜Oshipay開発者',
  display_name = 'あさぎり｜Oshipay開発者',
  slug         = 'asagiri',
  bio          = 'OshiPayで推し活をもっと楽しく！世界中から応援できます🔥',
  genre        = 'OshiPay開発者'
WHERE acct_id = 'acct_1T6prLJxxP0VtABn';

-- ========================================
-- 10. payout_enabled 初期値セット
-- ========================================
-- ✅ 口座登録完了ユーザー
UPDATE creators SET payout_enabled = TRUE
WHERE stripe_acct_id IN (
    'acct_1TCUnRF6jv27DC6h', 'acct_1TCNyKFSClrXOIH7', 'acct_1TCN2GF0fYyT8NjG',
    'acct_1TC7Ex2UmQw74oow', 'acct_1TCVccFCaBZsjwdF', 'acct_1TCZhmFP9HLcZjzP',
    'acct_1TCreEF7drpwGYF1', 'acct_1TCsIv2ZAnB0zI8R', 'acct_1TCt1SFXHSRnTSo6',
    'acct_1TCt8kJuJixC5HRy', 'acct_1TC7JDFZ5pcSXrW3', 'acct_1TD38K2ayG13ne5r',
    'acct_1T6prLJxxP0VtABn'
)
   OR acct_id IN (
    'acct_1TCUnRF6jv27DC6h', 'acct_1TCNyKFSClrXOIH7', 'acct_1TCN2GF0fYyT8NjG',
    'acct_1TC7Ex2UmQw74oow', 'acct_1TCVccFCaBZsjwdF', 'acct_1TCZhmFP9HLcZjzP',
    'usr_e0d308fabb3c4109',  'usr_27c74061f0ab429c',  'usr_bf8b5ebbb4be4cd3',
    'usr_3a09974a1d474f3d',  'acct_1TC7JDFZ5pcSXrW3', 'usr_cb2476d477df4b91',
    'acct_1T6prLJxxP0VtABn'
);

-- ⚠️ 口座登録未完了ユーザー
UPDATE creators SET payout_enabled = FALSE
WHERE stripe_acct_id IN (
    'acct_1TCtRHF6Lm1tY3Ea', 'acct_1TCz5A2WZY3wXzOu', 'acct_1TCzP2F4jdIAVDWT',
    'acct_1TCz522Wp5Q62jZz', 'acct_1TD289FFePLI48P7'
)
   OR acct_id IN (
    'usr_8f18d19400544dd6', 'usr_f99a9af1545243f2', 'usr_b940b238b21f405f',
    'usr_fed1ecc7c26a470c', 'usr_7bd0d92669634327'
);

-- ========================================
-- 11. データ修正（幽霊エントリ）
-- ========================================
-- ニコ太郎の支払い記録を正しいacct_idに修正
UPDATE supports
SET creator_acct = 'usr_cb2476d477df4b91'
WHERE creator_acct = 'acct_1TD38K2ayG13ne5r';

-- ========================================
-- スキーマキャッシュ強制リロード
-- ========================================
NOTIFY pgrst, 'reload schema';
