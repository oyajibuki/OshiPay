import streamlit as st
import os
import base64

# ── 1. 基本設定 ──
st.set_page_config(
    page_title="OshiPay - Smart LP",
    layout="wide",
    initial_sidebar_state="collapsed",
)

def read_html_file(file_path):
    """HTMLファイルを読み込む"""
    try:
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(cur_dir, file_path)
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"

import streamlit.components.v1 as components

# ── 2. LP表示ロジック ──
def render_native_lp(html_content):
    """
    Streamlitのiframe制限を突破する「Parent DOM Injection」方式
    """
    if not html_content or html_content.startswith("Error"):
        st.error(f"HTMLの読み込みに失敗しました: {html_content}")
        return

    b64_html = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
    
    components.html(f"""
    <script>
    (function() {{
        const b64Data = "{b64_html}";
        
        try {{
            const binStr = window.atob(b64Data);
            const bytes = new Uint8Array(binStr.length);
            for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i);
            const rawHtml = new TextDecoder().decode(bytes);

            const parser = new DOMParser();
            const doc = parser.parseFromString(rawHtml, 'text/html');
            const pDoc = window.parent.document;
            
            // 1. ラッパー作成とクラス移植
            let wrapper = pDoc.getElementById('oshi-lp-fullscreen-wrapper');
            if (!wrapper) {{
                wrapper = pDoc.createElement('div');
                wrapper.id = 'oshi-lp-fullscreen-wrapper';
                pDoc.body.appendChild(wrapper);
            }}
            // LPのbodyクラスをラッパーにコピー（デザイン再現のため）
            wrapper.className = doc.body.className;
            wrapper.style.backgroundColor = "#0a0a0f"; // 強制指定

            // 2. スタイル設定（StreamlitのUIを消去）
            const styleId = 'oshi-native-style-override';
            let styleEl = pDoc.getElementById(styleId);
            if (!styleEl) {{
                styleEl = pDoc.createElement('style');
                styleEl.id = styleId;
                pDoc.head.appendChild(styleEl);
            }}
            styleEl.textContent = `
                header, .stToolbar, .stDecoration, [data-testid="stHeader"], #root > div:nth-child(1) {{
                    display: none !important;
                }}
                #oshi-lp-fullscreen-wrapper {{
                    position: fixed;
                    top: 0; left: 0;
                    width: 100vw; height: 100vh;
                    overflow-y: auto;
                    z-index: 999999;
                }}
                /* 既存のスクロールバーを隠す */
                body {{ overflow: hidden !important; }}
            `;
            
            // 3. CSSの移植
            doc.querySelectorAll('link, style').forEach(el => pDoc.head.appendChild(el.cloneNode(true)));
            
            // 4. 内容の注入
            wrapper.innerHTML = doc.body.innerHTML;
            
            // 5. スクリプトの実行
            doc.querySelectorAll('script').forEach(oldScript => {{
                const newScript = pDoc.createElement('script');
                if (oldScript.src) newScript.src = oldScript.src;
                if (oldScript.textContent) newScript.textContent = oldScript.textContent;
                pDoc.body.appendChild(newScript);
            }});

            // 6. Intersection Observer 等が DOMContentLoaded で動かない場合のための手動発火
            // (Lucideの初期化なども含む)
            setTimeout(() => {{
                if (typeof window.parent.lucide !== 'undefined') {{
                    window.parent.lucide.createIcons();
                }}
                // スクロールイベントを強制的に発火させてアニメーションを開始
                window.parent.dispatchEvent(new Event('scroll'));
            }}, 500);

            // 7. リンク制御
            wrapper.addEventListener('click', function(e) {{
                const link = e.target.closest('a');
                if (link) {{
                    const href = link.getAttribute('href');
                    if (href && (href.startsWith('?') || href.includes('streamlit.app'))) {{
                        e.preventDefault();
                        window.parent.location.href = href;
                    }}
                }}
            }});

        }} catch(e) {{
            console.error("Injection failed:", e);
        }}
    }})();
    </script>
    """, height=0)
    
    st.markdown("""
    <style>
        body, .main {{ background-color: #0a0a0f !important; }}
        header, .stToolbar {{ display: none !important; }}
    </style>
    """, unsafe_allow_html=True)

# ── 3. メイン制御 ──
page = st.query_params.get("page", "lp")

if page == "lp":
    lp_content = read_html_file("oshipay-lp/index.html")
    render_native_lp(lp_content)
else:
    # 通常のページ表示（検証用）
    st.title(f"🚀 {page.capitalize()} ページ")
    st.info("これはiframeなしのネイティブ環境での表示テストです。")
    if st.button("LPに戻る"):
        st.query_params.clear()
        st.rerun()
