-- ============================================
-- OshiPay 追加/更新（一時的・実行済み管理）
-- 実行したらコメントアウトか削除してOK
-- ============================================

-- ----------------------------------------
-- Discord Bot ログテーブル作成
-- 実行日: 2026-03-27
-- ----------------------------------------
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

ALTER TABLE public.bot_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public insert bot_logs" ON public.bot_logs FOR INSERT WITH CHECK (true);
CREATE POLICY "Public select bot_logs" ON public.bot_logs FOR SELECT USING (true);

NOTIFY pgrst, 'reload schema';

-- ----------------------------------------
-- payout_enabled 初期値セット
-- 実行日: 2026-xx-xx
-- ----------------------------------------

-- ✅ 口座登録完了
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

-- ⚠️ 口座登録未完了
UPDATE creators SET payout_enabled = FALSE
WHERE stripe_acct_id IN (
    'acct_1TCtRHF6Lm1tY3Ea', 'acct_1TCz5A2WZY3wXzOu', 'acct_1TCzP2F4jdIAVDWT',
    'acct_1TCz522Wp5Q62jZz', 'acct_1TD289FFePLI48P7'
)
   OR acct_id IN (
    'usr_8f18d19400544dd6', 'usr_f99a9af1545243f2', 'usr_b940b238b21f405f',
    'usr_fed1ecc7c26a470c', 'usr_7bd0d92669634327'
);

-- ----------------------------------------
-- データ修正（幽霊エントリ）
-- ニコ太郎の支払い記録を正しいacct_idに修正
-- 実行日: 2026-xx-xx
-- ----------------------------------------
UPDATE supports
SET creator_acct = 'usr_cb2476d477df4b91'
WHERE creator_acct = 'acct_1TD38K2ayG13ne5r';

-- ----------------------------------------
-- supporter_id マイグレーション（sup_BBB → sup_AAA）
-- 実行日: 2026-xx-xx
-- ----------------------------------------
UPDATE supports         SET supporter_id = 'sup_AAA' WHERE supporter_id = 'sup_BBB';
UPDATE pending_supports SET supporter_id = 'sup_AAA' WHERE supporter_id = 'sup_BBB';
DELETE FROM supporters         WHERE supporter_id = 'sup_BBB';
DELETE FROM supporter_accounts WHERE supporter_id = 'sup_BBB';

-- ----------------------------------------
-- show_on_profile 一括有効化
-- 実行日: 2026-xx-xx
-- ----------------------------------------
UPDATE supports SET show_on_profile = TRUE
WHERE show_on_profile IS NULL OR show_on_profile = FALSE;

-- ----------------------------------------
-- supporter_accounts へのデータ移行（supporters から）
-- 実行日: 2026-xx-xx
-- ----------------------------------------
INSERT INTO supporter_accounts (supporter_id, email, password_hash)
SELECT supporter_id, email, password_hash
FROM supporters
WHERE email IS NOT NULL AND email != ''
ON CONFLICT DO NOTHING;
