-- ============================================
-- OshiPay DB スキーマ（固定・冪等）
-- 何度実行しても安全
-- ============================================

-- ========================================
-- 1. テーブル作成
-- ========================================

CREATE TABLE IF NOT EXISTS public.supports (
    id               BIGSERIAL    PRIMARY KEY,
    support_id       UUID         UNIQUE NOT NULL,
    creator_acct     TEXT         NOT NULL,
    creator_name     TEXT         NOT NULL,
    amount           INTEGER      NOT NULL,
    message          TEXT         DEFAULT '',
    created_at       TIMESTAMPTZ  DEFAULT NOW(),
    reply_emoji      TEXT,
    reply_text       TEXT,
    replied_at       TIMESTAMPTZ,
    owner_id         TEXT,
    is_listed        BOOLEAN      DEFAULT FALSE,
    list_price       INTEGER,
    supporter_id     TEXT,
    creator_rank     INTEGER,
    show_on_profile  BOOLEAN      DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS public.creators (
    acct_id         TEXT PRIMARY KEY,
    password_hash   TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    name            TEXT,
    display_name    TEXT,
    slug            TEXT UNIQUE,
    bio             TEXT DEFAULT '',
    genre           TEXT DEFAULT '',
    photo_url       TEXT DEFAULT '',
    sns_links       JSONB DEFAULT '{}',
    x_url           TEXT,
    instagram_url   TEXT,
    tiktok_url      TEXT,
    qr_url          TEXT,
    is_deleted      BOOLEAN DEFAULT FALSE,
    profile_done    BOOLEAN DEFAULT FALSE,
    email           TEXT,
    stripe_acct_id  TEXT,
    payout_enabled  BOOLEAN DEFAULT FALSE,
    supporter_id    TEXT
);

CREATE TABLE IF NOT EXISTS public.supporters (
    supporter_id     TEXT PRIMARY KEY,
    display_name     TEXT,
    created_at       TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    password_hash    TEXT,
    email            TEXT,
    creator_acct_id  TEXT
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
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    creator_acct     TEXT NOT NULL,
    amount           INTEGER NOT NULL DEFAULT 0,
    message          TEXT,
    contact_info     TEXT,
    supporter_email  TEXT,
    supporter_id     TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    expires_at       TIMESTAMPTZ DEFAULT (now() + interval '72 hours'),
    status           TEXT DEFAULT 'pending',
    reminded_at      TIMESTAMPTZ,
    reservation_no   INTEGER,
    locked_rank      INTEGER
);

CREATE TABLE IF NOT EXISTS public.supporter_accounts (
    supporter_id       TEXT PRIMARY KEY DEFAULT ('sup_' || substr(gen_random_uuid()::text, 1, 16)),
    email              TEXT UNIQUE NOT NULL,
    password_hash      TEXT,
    stripe_customer_id TEXT,
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.bot_logs (
    id           BIGSERIAL    PRIMARY KEY,
    question     TEXT         NOT NULL,
    answer       TEXT,
    answered     BOOLEAN      DEFAULT FALSE,
    channel_name TEXT,
    user_id      TEXT,
    guild_id     TEXT,
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);

-- ========================================
-- 2. インデックス
-- ========================================

CREATE INDEX IF NOT EXISTS idx_supports_supporter_id ON public.supports(supporter_id);
CREATE INDEX IF NOT EXISTS idx_creators_slug         ON public.creators(slug);
CREATE INDEX IF NOT EXISTS idx_creators_is_deleted   ON public.creators(is_deleted);

-- ========================================
-- 3. RLS 有効化
-- ========================================

ALTER TABLE public.supports           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.creators           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.supporters         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.deleted_slugs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stamps             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pending_supports   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.supporter_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bot_logs           ENABLE ROW LEVEL SECURITY;

-- ========================================
-- 4. RLS ポリシー（DROP → CREATE で冪等）
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
DROP POLICY IF EXISTS "Public insert bot_logs"       ON public.bot_logs;
DROP POLICY IF EXISTS "Public select bot_logs"       ON public.bot_logs;
CREATE POLICY "Public insert bot_logs"               ON public.bot_logs           FOR INSERT         WITH CHECK (true);
CREATE POLICY "Public select bot_logs"               ON public.bot_logs           FOR SELECT         USING (true);

-- ========================================
-- 5. Storage ポリシー（DROP → CREATE で冪等）
-- ========================================

DROP POLICY IF EXISTS "public upload creator-photos" ON storage.objects;
DROP POLICY IF EXISTS "public update creator-photos" ON storage.objects;
DROP POLICY IF EXISTS "public read creator-photos"   ON storage.objects;

CREATE POLICY "public upload creator-photos" ON storage.objects FOR INSERT TO anon WITH CHECK (bucket_id = 'creator-photos');
CREATE POLICY "public update creator-photos" ON storage.objects FOR UPDATE TO anon USING  (bucket_id = 'creator-photos');
CREATE POLICY "public read creator-photos"   ON storage.objects FOR SELECT TO anon USING  (bucket_id = 'creator-photos');

-- ========================================
-- 6. 初期データ（開発者アカウント）
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
-- スキーマキャッシュ強制リロード
-- ========================================

NOTIFY pgrst, 'reload schema';
