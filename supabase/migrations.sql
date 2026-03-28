-- ============================================
-- OshiPay 追加/更新（一時的・実行済み管理）
-- ✅ = 実行済み・schema.sql に反映済み
-- ⚠️ = データ操作（再実行注意）
-- ============================================

-- ============================================
-- ✅ スキーマ変更（すべてschema.sqlに反映済み）
-- 再実行不要・記録のみ
-- ============================================

-- ✅ supporter_accounts に google_sub 追加（2026-03-28）
-- ALTER TABLE public.supporter_accounts ADD COLUMN IF NOT EXISTS google_sub TEXT UNIQUE;

-- ✅ supporters に google_sub 追加（2026-03-28）
-- ALTER TABLE public.supporters ADD COLUMN IF NOT EXISTS google_sub TEXT UNIQUE;

-- ✅ creators に google_sub 追加（2026-03-29）
-- ALTER TABLE public.creators ADD COLUMN IF NOT EXISTS google_sub TEXT UNIQUE;

-- ✅ Discord OAuth 対応 discord_sub 追加（2026-03-29）
-- ALTER TABLE public.supporters         ADD COLUMN IF NOT EXISTS discord_sub TEXT UNIQUE;
-- ALTER TABLE public.supporter_accounts ADD COLUMN IF NOT EXISTS discord_sub TEXT UNIQUE;
-- ALTER TABLE public.creators           ADD COLUMN IF NOT EXISTS discord_sub TEXT UNIQUE;

-- ✅ bot_logs テーブル作成（2026-03-27）→ schema.sql に統合済み

-- ============================================
-- ⚠️ データ修正（一度のみ実行・記録として残す）
-- ============================================

-- ----------------------------------------
-- ⚠️ payout_enabled 初期値セット（2026-03-27・実行済み）
-- ----------------------------------------
-- UPDATE creators SET payout_enabled = TRUE
-- WHERE stripe_acct_id IN (
--     'acct_1TCUnRF6jv27DC6h', 'acct_1TCNyKFSClrXOIH7', 'acct_1TCN2GF0fYyT8NjG',
--     'acct_1TC7Ex2UmQw74oow', 'acct_1TCVccFCaBZsjwdF', 'acct_1TCZhmFP9HLcZjzP',
--     'acct_1TCreEF7drpwGYF1', 'acct_1TCsIv2ZAnB0zI8R', 'acct_1TCt1SFXHSRnTSo6',
--     'acct_1TCt8kJuJixC5HRy', 'acct_1TC7JDFZ5pcSXrW3', 'acct_1TD38K2ayG13ne5r',
--     'acct_1T6prLJxxP0VtABn'
-- )
--    OR acct_id IN (
--     'acct_1TCUnRF6jv27DC6h', 'acct_1TCNyKFSClrXOIH7', 'acct_1TCN2GF0fYyT8NjG',
--     'acct_1TC7Ex2UmQw74oow', 'acct_1TCVccFCaBZsjwdF', 'acct_1TCZhmFP9HLcZjzP',
--     'usr_e0d308fabb3c4109',  'usr_27c74061f0ab429c',  'usr_bf8b5ebbb4be4cd3',
--     'usr_3a09974a1d474f3d',  'acct_1TC7JDFZ5pcSXrW3', 'usr_cb2476d477df4b91',
--     'acct_1T6prLJxxP0VtABn'
-- );
-- UPDATE creators SET payout_enabled = FALSE
-- WHERE stripe_acct_id IN (
--     'acct_1TCtRHF6Lm1tY3Ea', 'acct_1TCz5A2WZY3wXzOu', 'acct_1TCzP2F4jdIAVDWT',
--     'acct_1TCz522Wp5Q62jZz', 'acct_1TD289FFePLI48P7'
-- )
--    OR acct_id IN (
--     'usr_8f18d19400544dd6', 'usr_f99a9af1545243f2', 'usr_b940b238b21f405f',
--     'usr_fed1ecc7c26a470c', 'usr_7bd0d92669634327'
-- );

-- ----------------------------------------
-- ⚠️ 幽霊エントリ修正：supports の creator_acct 付け替え（2026-03-27・実行済み）
-- ----------------------------------------
-- UPDATE supports
-- SET creator_acct = 'usr_cb2476d477df4b91'
-- WHERE creator_acct = 'acct_1TD38K2ayG13ne5r';

-- ----------------------------------------
-- ⚠️ supporter_id マイグレーション sup_BBB → sup_AAA（2026-03-27・実行済み）
-- ----------------------------------------
-- UPDATE supports         SET supporter_id = 'sup_AAA' WHERE supporter_id = 'sup_BBB';
-- UPDATE pending_supports SET supporter_id = 'sup_AAA' WHERE supporter_id = 'sup_BBB';
-- DELETE FROM supporters         WHERE supporter_id = 'sup_BBB';
-- DELETE FROM supporter_accounts WHERE supporter_id = 'sup_BBB';

-- ----------------------------------------
-- ⚠️ show_on_profile 一括有効化（2026-03-27・実行済み）
-- ----------------------------------------
-- UPDATE supports SET show_on_profile = TRUE
-- WHERE show_on_profile IS NULL OR show_on_profile = FALSE;

-- ----------------------------------------
-- ⚠️ supporter_accounts へのデータ移行（2026-03-27・実行済み）
-- ----------------------------------------
-- INSERT INTO supporter_accounts (supporter_id, email, password_hash)
-- SELECT supporter_id, email, password_hash
-- FROM supporters
-- WHERE email IS NOT NULL AND email != ''
-- ON CONFLICT DO NOTHING;

-- ----------------------------------------
-- ⚠️ Google sub 付け替え：sup_056dac79 → sup_32dc1b6b（2026-03-28・実行済み）
-- ----------------------------------------
-- UPDATE supporter_accounts
-- SET google_sub = (SELECT google_sub FROM supporter_accounts WHERE supporter_id = 'sup_056dac79')
-- WHERE supporter_id = 'sup_32dc1b6b';
-- UPDATE supporter_accounts SET google_sub = NULL WHERE supporter_id = 'sup_056dac79';

-- ----------------------------------------
-- ⚠️ sup_32dc1b6b の email スペース修正（2026-03-28・実行済み）
-- ----------------------------------------
-- UPDATE supporters       SET email = 'oyajibuki@gmail.com' WHERE supporter_id = 'sup_32dc1b6b';
-- UPDATE supporter_accounts SET email = 'oyajibuki@gmail.com' WHERE supporter_id = 'sup_32dc1b6b';

-- ============================================
-- 🆕 未実行・今後の作業用はここに追記する
-- ============================================

-- LINE OAuth 対応 line_sub 追加（2026-03-30）
ALTER TABLE public.supporters         ADD COLUMN IF NOT EXISTS line_sub TEXT UNIQUE;
ALTER TABLE public.supporter_accounts ADD COLUMN IF NOT EXISTS line_sub TEXT UNIQUE;
ALTER TABLE public.creators           ADD COLUMN IF NOT EXISTS line_sub TEXT UNIQUE;

NOTIFY pgrst, 'reload schema';
