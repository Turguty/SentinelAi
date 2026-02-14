let currentPage = 1;
let sourceChart = null;

document.addEventListener('DOMContentLoaded', () => {
    fetchNews(1);
    updateStats();
});

async function fetchNews(page = 1) {
    currentPage = page;
    const search = document.getElementById('search-input').value;
    try {
        const res = await fetch(`/api/news?page=${page}&search=${encodeURIComponent(search)}`);
        const data = await res.json();
        renderNews(data.news);
        renderPagination(data.total, data.per_page, data.current_page);
    } catch (e) { console.error("Haber hatası:", e); }
}

function renderNews(newsItems) {
    const feed = document.getElementById('news-feed');
    feed.innerHTML = '';
    newsItems.forEach(item => {
        let level = (item.ai_analysis || "").includes('KRITIK') ? 'critical' :
            (item.ai_analysis || "").includes('ORTA') ? 'medium' : 'low';

        const card = document.createElement('div');
        card.className = `news-card ${level}`;
        card.innerHTML = `
            <div class="card-meta"><span class="threat-badge badge-${level}">${level.toUpperCase()}</span><small>${item.source}</small></div>
            <h3>${item.title}</h3>
            <div class="card-actions">
                <a href="${item.link}" target="_blank" class="btn-link">🌐 Git</a>
                <button class="btn-analyze" onclick="analyzeNews('${item.title.replace(/'/g, "\\'")}', '${item.link}')">
                    ${item.ai_analysis ? '📂 Arşiv' : '🧠 Analiz'}
                </button>
            </div>`;
        feed.appendChild(card);
    });
}

function renderPagination(total, perPage, current) {
    const container = document.getElementById('pagination-container');
    container.innerHTML = '';
    const totalPages = Math.ceil(total / perPage);

    // Sadece 5 sayfa göster (veya hepsi)
    for (let i = 1; i <= Math.min(totalPages, 10); i++) {
        const btn = document.createElement('button');
        btn.innerText = i;
        btn.className = i === current ? 'active' : '';
        btn.onclick = () => fetchNews(i);
        container.appendChild(btn);
    }
}

async function updateStats() {
    try {
        // 1. Kaynak Dağılımı (Doughnut Chart)
        const resStats = await fetch('/api/stats');
        const statsData = await resStats.json();
        const srcLabels = statsData.sources.map(s => s.source);
        const srcCounts = statsData.sources.map(s => s.count);

        const ctxSrc = document.getElementById('sourceChart').getContext('2d');
        if (sourceChart) sourceChart.destroy();
        sourceChart = new Chart(ctxSrc, {
            type: 'doughnut',
            data: {
                labels: srcLabels,
                datasets: [{
                    data: srcCounts,
                    backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { color: '#90949a', font: { size: 10 }, usePointStyle: true, padding: 15 }
                    }
                },
                layout: { padding: { top: 10, bottom: 10 } }
            }
        });

        // 2. Haber Yoğunluğu (Bar Chart)
        const resInt = await fetch('/api/intensity');
        const intData = await resInt.json();
        const intLabels = intData.intensity.map(i => i.date);
        const intCounts = intData.intensity.map(i => i.count);

        const ctxBar = document.getElementById('barChart').getContext('2d');
        new Chart(ctxBar, {
            type: 'bar',
            data: {
                labels: intLabels,
                datasets: [{
                    label: 'Haber Sayısı',
                    data: intCounts,
                    backgroundColor: 'rgba(59, 130, 246, 0.5)',
                    borderColor: '#3b82f6',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#90949a' } },
                    x: { grid: { display: false }, ticks: { color: '#90949a' } }
                },
                plugins: { legend: { display: false } }
            }
        });

    } catch (e) { console.error("Grafik hatası:", e); }
}

async function analyzeNews(title, link) {
    document.getElementById('analysis-panel').classList.remove('hidden');
    document.getElementById('analysis-text').innerText = "Analiz ediliyor...";
    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, link })
        });
        const data = await res.json();
        document.getElementById('analysis-text').innerText = data.analysis;
        fetchNews(currentPage);
    } catch (e) { document.getElementById('analysis-text').innerText = "Hata oluştu."; }
}

async function queryCVE() {
    const cveId = document.getElementById('cve-input').value.trim();
    if (!cveId) return alert("Lütfen bir CVE ID girin (Örn: CVE-2024-1234)");

    document.getElementById('analysis-panel').classList.remove('hidden');
    const display = document.getElementById('analysis-text');
    display.innerHTML = `<div class="loading">🔍 <b>${cveId}</b> araştırılıyor ve AI analizi hazırlanıyor...</div>`;

    try {
        const res = await fetch(`/api/cve?id=${cveId}`);
        const data = await res.json();
        if (data.error) {
            display.innerHTML = `<p style="color: #ef4444;">❌ Hata: ${data.error}</p>`;
        } else {
            display.innerHTML = `
                <div class="cve-result">
                    <h4>${data.id} Analysis</h4>
                    <p><b>CVSS:</b> <span class="badge-${parseFloat(data.cvss) > 7 ? 'critical' : 'medium'}">${data.cvss}</span></p>
                    <p><b>Özet:</b> ${data.summary}</p>
                    <hr>
                    <div class="ai-commentary">
                        <h5>🧠 AI Güvenlik Analizi</h5>
                        ${data.ai_comment.replace(/\n/g, '<br>')}
                    </div>
                </div>`;
        }
    } catch (e) { display.innerHTML = "Sistem hatası oluştu."; }
}

async function queryIP() {
    const ip = document.getElementById('ip-input').value.trim();
    if (!ip) return alert("Lütfen bir IP adresi girin");

    document.getElementById('analysis-panel').classList.remove('hidden');
    const display = document.getElementById('analysis-text');
    display.innerHTML = `🔍 <b>${ip}</b> sorgulanıyor...`;

    try {
        const res = await fetch(`/api/ip?ip=${ip}`);
        const data = await res.json();
        if (data.error) {
            display.innerHTML = `<p style="color: #ef4444;">❌ Hata: ${data.error}</p>`;
        } else {
            display.innerHTML = `
                <div class="ip-result">
                    <h4>IP İstihbarat Raporu: ${data.ip}</h4>
                    <p>📍 <b>Konum:</b> ${data.location}</p>
                    <p>🏢 <b>Servis Sağlayıcı (ISP):</b> ${data.isp}</p>
                    <p>🏭 <b>Organizasyon:</b> ${data.org}</p>
                    <p>🛡️ <b>AS:</b> ${data.as}</p>
                </div>`;
        }
    } catch (e) { display.innerHTML = "Sistem hatası oluştu."; }
}

function closeAnalysis() { document.getElementById('analysis-panel').classList.add('hidden'); }
function searchNews(e, page = 1) {
    if (e && e.type === 'keyup' && e.key !== 'Enter') return;
    fetchNews(page);
}
