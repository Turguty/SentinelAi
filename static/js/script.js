let sourceChart = null;
let categoryChart = null;
let barChart = null;

document.addEventListener('DOMContentLoaded', () => {
    fetchNews(1);
    updateStats();
    updateAIStatus();
    // Her 30 saniyede bir AI durumunu güncelle
    setInterval(updateAIStatus, 30000);
    updateSystemHealth();
    setInterval(updateSystemHealth, 10000);
});

async function updateSystemHealth() {
    try {
        const res = await fetch('/api/system/health');
        const data = await res.json();
        document.getElementById('cpu-val').innerText = `${data.cpu}%`;
        document.getElementById('ram-val').innerText = `${data.ram}%`;

        // Kritik durum kontrolü (Görsel uyarı)
        document.getElementById('cpu-val').style.color = data.cpu > 80 ? '#ef4444' : '#3b82f6';
        document.getElementById('ram-val').style.color = data.ram > 80 ? '#ef4444' : '#3b82f6';

    } catch (e) { console.error("Sistem sağlık hatası:", e); }
}


async function updateAIStatus() {
    try {
        const res = await fetch('/api/ai_status');
        const data = await res.json();
        const statusBar = document.getElementById('ai-status-bar');
        statusBar.innerHTML = '';

        for (const [service, status] of Object.entries(data)) {
            const item = document.createElement('div');
            item.className = 'ai-status-item';
            item.title = status === 'active' ? 'Aktif' : (status === 'cooldown' ? 'Soğuma Modunda' : 'Anahtar Yok');
            item.innerHTML = `
                <span class="ai-status-dot ${status}"></span>
                ${service.charAt(0).toUpperCase() + service.slice(1, 3)}
            `;
            statusBar.appendChild(item);
        }
    } catch (e) { console.error("AI durum güncelleme hatası:", e); }
}


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

        // 3. Tehdit Kategorileri (Horizontal Bar Chart)
        const resCat = await fetch('/api/stats/categories');
        const catData = await resCat.json();
        const catLabels = catData.categories.map(c => c.category);
        const catCounts = catData.categories.map(c => c.count);

        const ctxCat = document.getElementById('categoryChart').getContext('2d');
        if (categoryChart) categoryChart.destroy();
        categoryChart = new Chart(ctxCat, {
            type: 'bar',
            data: {
                labels: catLabels,
                datasets: [{
                    label: 'Olay Sayısı',
                    data: catCounts,
                    backgroundColor: '#8b5cf6',
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#90949a' } },
                    y: { grid: { display: false }, ticks: { color: '#e1e1e1', font: { weight: 'bold' } } }
                }
            }
        });

    } catch (e) { console.error("Grafik hatası:", e); }

}

async function queryDNS() {
    const domain = document.getElementById('dns-input').value.trim();
    if (!domain) return alert("Lütfen bir domain girin");

    document.getElementById('analysis-panel').classList.remove('hidden');
    const display = document.getElementById('analysis-text');
    display.innerHTML = `🔍 <b>${domain}</b> DNS kayıtları sorgulanıyor...`;

    try {
        const res = await fetch(`/api/dns?domain=${domain}`);
        const data = await res.json();
        if (data.error) {
            display.innerHTML = `<p style="color: #ef4444;">❌ Hata: ${data.error}</p>`;
        } else {
            display.innerHTML = `
                <div class="dns-result">
                    <h4>DNS Raporu: ${data.domain}</h4>
                    <hr>
                    <div class="dns-section">
                        <h5>🌐 A Kayıtları (IP)</h5>
                        <ul>${data.records.A.length ? data.records.A.map(r => `<li>${r}</li>`).join('') : '<li>Kayıt yok</li>'}</ul>
                    </div>
                    <div class="dns-section">
                        <h5>📧 MX Kayıtları (Mail)</h5>
                        <ul>${data.records.MX.length ? data.records.MX.map(r => `<li>${r}</li>`).join('') : '<li>Kayıt yok</li>'}</ul>
                    </div>
                    <div class="dns-section">
                        <h5>🔗 CNAME Kayıtları</h5>
                        <ul>${data.records.CNAME.length ? data.records.CNAME.map(r => `<li>${r}</li>`).join('') : '<li>Kayıt yok</li>'}</ul>
                    </div>
                    <div class="dns-section">
                        <h5>📝 TXT Kayıtları</h5>
                        <ul>${data.records.TXT.length ? data.records.TXT.map(r => `<li>${r}</li>`).join('') : '<li>Kayıt yok</li>'}</ul>
                    </div>
                    <div class="dns-section">
                        <h5>🔀 Name Server (NS)</h5>
                        <ul>${data.records.NS.length ? data.records.NS.map(r => `<li>${r}</li>`).join('') : '<li>Kayıt yok</li>'}</ul>
                    </div>
                </div>`;

        }
    } catch (e) { display.innerHTML = "Sistem hatası oluştu."; }
}

async function queryWhois() {
    const domain = document.getElementById('whois-input').value.trim();
    if (!domain) return alert("Lütfen bir domain girin");

    document.getElementById('analysis-panel').classList.remove('hidden');
    const display = document.getElementById('analysis-text');
    display.innerHTML = `🔍 <b>${domain}</b> WHOIS bilgileri çekiliyor...`;

    try {
        const res = await fetch(`/api/whois?domain=${domain}`);
        const data = await res.json();
        if (data.error) {
            display.innerHTML = `<p style="color: #ef4444;">❌ Hata: ${data.error}</p>`;
        } else {
            display.innerHTML = `
                <div class="whois-result">
                    <h4>WHOIS Raporu: ${data.domain}</h4>
                    <hr>
                    <p><b>🏢 Kayıt Kuruluşu (Registrar):</b> ${data.registrar || 'Bilinmiyor'}</p>
                    <p><b>📅 Oluşturulma:</b> ${data.creation_date}</p>
                    <p><b>⌛ Bitiş:</b> ${data.expiration_date}</p>
                    <p><b>📜 Durum:</b> ${data.status}</p>
                    <br>
                    <h5>🌐 Name Servers</h5>
                    <ul>${data.name_servers.map(ns => `<li>${ns}</li>`).join('')}</ul>
                </div>`;
        }
    } catch (e) { display.innerHTML = "Sistem hatası oluştu."; }
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
        // İndirme butonu ekle
        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'btn-report';
        downloadBtn.style.marginTop = '10px';
        downloadBtn.innerText = '💾 Analizi İndir (.md)';
        downloadBtn.onclick = () => {
            const blob = new Blob([data.analysis], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `sentinel-analiz-${new Date().getTime()}.md`;
            a.click();
        };
        document.getElementById('analysis-text').appendChild(document.createElement('br'));
        document.getElementById('analysis-text').appendChild(downloadBtn);

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
