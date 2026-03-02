/* ============================================
   OshiPay — Frontend Logic
   ============================================ */

// ── QR Generation (Dashboard) ──
function initDashboard() {
    const form = document.getElementById('qr-form');
    const resultArea = document.getElementById('qr-result');

    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const nameInput = document.getElementById('creator-name');
        const userIdInput = document.getElementById('user-id');
        const btn = form.querySelector('.btn-primary');

        const name = nameInput.value.trim();
        if (!name) {
            nameInput.focus();
            return;
        }

        // Loading state
        btn.disabled = true;
        const originalText = btn.innerHTML;
        btn.innerHTML = '<div class="spinner" style="display:inline-block;"></div> 生成中...';

        try {
            const res = await fetch('/api/generate-qr', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    user_id: userIdInput ? userIdInput.value.trim() : '',
                }),
            });

            const data = await res.json();

            resultArea.innerHTML = `
        <div class="qr-container animate-fade-in">
          <div class="qr-frame">
            <img src="data:image/png;base64,${data.qr_image}" alt="QRコード" />
          </div>
          <p class="qr-url">${data.support_url}</p>
          <div style="display: flex; gap: 10px; width: 100%;">
            <button class="btn btn-secondary" onclick="copyUrl('${data.support_url}')" style="flex:1;">
              📋 URLコピー
            </button>
            <a href="data:image/png;base64,${data.qr_image}" download="oshiPay-qr-${data.user_id}.png" class="btn btn-secondary" style="flex:1;">
              💾 QR保存
            </a>
          </div>
        </div>
      `;
            resultArea.style.display = 'block';
        } catch (err) {
            console.error(err);
            showToast('エラーが発生しました');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    });
}


// ── Support (Tipping) Page ──
function initSupport() {
    const amountBtns = document.querySelectorAll('.amount-btn');
    const supportBtn = document.getElementById('support-btn');
    const selectedDisplay = document.getElementById('selected-amount');
    const customWrapper = document.getElementById('custom-amount-wrapper');
    const customInput = document.getElementById('custom-amount');

    if (!amountBtns.length) return;

    let selectedAmount = null;

    amountBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const value = btn.dataset.amount;

            // Custom amount toggle
            if (value === 'custom') {
                amountBtns.forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                customWrapper.classList.add('show');
                customInput.focus();
                selectedAmount = null;
                updateSelectedDisplay(null);
                return;
            }

            // Preset amount
            customWrapper.classList.remove('show');
            amountBtns.forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            selectedAmount = parseInt(value);
            updateSelectedDisplay(selectedAmount);

            // haptic-like visual feedback
            btn.style.transform = 'scale(1.05)';
            setTimeout(() => { btn.style.transform = ''; }, 150);
        });
    });

    // Custom amount input
    if (customInput) {
        customInput.addEventListener('input', () => {
            const val = parseInt(customInput.value);
            if (val >= 100) {
                selectedAmount = val;
                updateSelectedDisplay(val);
            }
        });
    }

    // Support button
    if (supportBtn) {
        supportBtn.addEventListener('click', async () => {
            // Check custom amount if custom is selected
            if (customWrapper.classList.contains('show')) {
                const val = parseInt(customInput.value);
                if (!val || val < 100) {
                    showToast('100円以上を入力してください');
                    customInput.focus();
                    return;
                }
                selectedAmount = val;
            }

            if (!selectedAmount) {
                showToast('金額を選んでください');
                return;
            }

            const userId = supportBtn.dataset.userId;
            const displayName = supportBtn.dataset.displayName;

            // Loading state
            supportBtn.disabled = true;
            const originalText = supportBtn.innerHTML;
            supportBtn.innerHTML = '<div class="spinner" style="display:inline-block;"></div> 決済ページへ移動中...';

            try {
                const res = await fetch('/api/create-checkout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        amount: selectedAmount,
                        user_id: userId,
                        display_name: displayName,
                    }),
                });

                const data = await res.json();

                if (data.checkout_url) {
                    window.location.href = data.checkout_url;
                } else {
                    showToast(data.error || 'エラーが発生しました');
                    supportBtn.disabled = false;
                    supportBtn.innerHTML = originalText;
                }
            } catch (err) {
                console.error(err);
                showToast('エラーが発生しました');
                supportBtn.disabled = false;
                supportBtn.innerHTML = originalText;
            }
        });
    }
}

function updateSelectedDisplay(amount) {
    const el = document.getElementById('selected-amount');
    if (!el) return;

    if (amount) {
        el.textContent = `¥${amount.toLocaleString()}`;
        el.classList.add('visible');
    } else {
        el.classList.remove('visible');
    }
}


// ── URL Copy ──
function copyUrl(url) {
    navigator.clipboard.writeText(url).then(() => {
        showToast('URLをコピーしました！');
    }).catch(() => {
        // Fallback
        const ta = document.createElement('textarea');
        ta.value = url;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showToast('URLをコピーしました！');
    });
}


// ── Toast ──
function showToast(message) {
    let toast = document.getElementById('toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.className = 'toast';
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
    }, 2500);
}


// ── Floating Particles ──
function initParticles() {
    const canvas = document.getElementById('particles-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let particles = [];
    let w, h;

    function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
    }

    resize();
    window.addEventListener('resize', resize);

    class Particle {
        constructor() {
            this.reset();
        }
        reset() {
            this.x = Math.random() * w;
            this.y = Math.random() * h;
            this.size = Math.random() * 2 + 0.5;
            this.speedX = (Math.random() - 0.5) * 0.3;
            this.speedY = (Math.random() - 0.5) * 0.3;
            this.opacity = Math.random() * 0.3 + 0.05;
            this.hue = Math.random() > 0.5 ? 270 : 330; // purple or pink
        }
        update() {
            this.x += this.speedX;
            this.y += this.speedY;
            if (this.x < 0 || this.x > w || this.y < 0 || this.y > h) {
                this.reset();
            }
        }
        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fillStyle = `hsla(${this.hue}, 80%, 65%, ${this.opacity})`;
            ctx.fill();
        }
    }

    for (let i = 0; i < 50; i++) {
        particles.push(new Particle());
    }

    function animate() {
        ctx.clearRect(0, 0, w, h);
        particles.forEach(p => {
            p.update();
            p.draw();
        });
        requestAnimationFrame(animate);
    }

    animate();
}


// ── Confetti (Success Page) ──
function initConfetti() {
    const canvas = document.getElementById('confetti-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let confetti = [];
    let w, h;

    function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
    }

    resize();
    window.addEventListener('resize', resize);

    const colors = ['#8b5cf6', '#ec4899', '#f97316', '#22d3ee', '#10b981', '#fbbf24'];

    class Confetto {
        constructor() {
            this.x = Math.random() * w;
            this.y = -20;
            this.size = Math.random() * 8 + 4;
            this.speedY = Math.random() * 3 + 2;
            this.speedX = (Math.random() - 0.5) * 4;
            this.rotation = Math.random() * 360;
            this.rotationSpeed = (Math.random() - 0.5) * 10;
            this.color = colors[Math.floor(Math.random() * colors.length)];
            this.opacity = 1;
        }
        update() {
            this.y += this.speedY;
            this.x += this.speedX;
            this.rotation += this.rotationSpeed;
            this.speedY += 0.05;
            if (this.y > h) this.opacity -= 0.02;
        }
        draw() {
            if (this.opacity <= 0) return;
            ctx.save();
            ctx.translate(this.x, this.y);
            ctx.rotate(this.rotation * Math.PI / 180);
            ctx.globalAlpha = this.opacity;
            ctx.fillStyle = this.color;
            ctx.fillRect(-this.size / 2, -this.size / 2, this.size, this.size * 0.6);
            ctx.restore();
        }
    }

    // Launch confetti in bursts
    let burstCount = 0;
    const burstInterval = setInterval(() => {
        for (let i = 0; i < 15; i++) {
            confetti.push(new Confetto());
        }
        burstCount++;
        if (burstCount > 6) clearInterval(burstInterval);
    }, 400);

    function animate() {
        ctx.clearRect(0, 0, w, h);
        confetti = confetti.filter(c => c.opacity > 0);
        confetti.forEach(c => {
            c.update();
            c.draw();
        });
        if (confetti.length > 0 || burstCount <= 6) {
            requestAnimationFrame(animate);
        }
    }

    animate();
}


// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    initParticles();
    initDashboard();
    initSupport();
    initConfetti();
});
