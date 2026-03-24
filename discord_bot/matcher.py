"""
OshiPay チャットBot — マッチングエンジン
==========================================
キーワード完全一致 → difflib ゆらぎ検出 の2段階で回答を探す。
"""

import re
import unicodedata
import difflib
from qa_data import QA_LIST


# ── テキスト正規化 ─────────────────────────────────────────────
def normalize(text: str) -> str:
    """全角→半角・大文字→小文字・記号除去・スペース除去"""
    text = unicodedata.normalize("NFKC", text)   # 全角英数→半角
    text = text.lower()
    text = re.sub(r"[？！。、・\s\-_/]", "", text)  # 記号・空白除去
    return text


# ── メインマッチング関数 ──────────────────────────────────────
def find_answer(query: str) -> str | None:
    """
    質問テキストを受け取り、最も近い回答を返す。
    マッチしない場合は None を返す。
    """
    q = normalize(query)
    if not q:
        return None

    best_score = 0.0
    best_answer = None

    for qa in QA_LIST:
        for kw in qa["keywords"]:
            kw_norm = normalize(kw)

            # ① 完全部分一致（最優先）
            if kw_norm in q or q in kw_norm:
                score = 1.0
            else:
                # ② difflib ゆらぎ（誤字・略語）
                score = difflib.SequenceMatcher(None, q, kw_norm).ratio()

            if score > best_score:
                best_score = score
                best_answer = qa["answer"]

    # 信頼度 0.55 未満は「わからない」として None を返す
    if best_score < 0.55:
        return None

    return best_answer
