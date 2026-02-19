let currentPage = 1;
let sourceChart = null;
let barChart = null;
let categoryChart = null;
let lastPendingCount = -1; // İlk yüklemede tetiklenmemesi için -1

// Merkezi Renk Paleti
const CATEGORY_COLORS = {
    'Malware': '#ef4444',        // Kırmızı
    'Ransomware': '#dc2626',     // Koyu kırmızı
    'Phishing': '#f59e0b',       // Turuncu
    'Vulnerability': '#8b5cf6',  // Mor
    'Breach': '#ec4899',         // Pembe
    'APT': '#6366f1',            // İndigo
    'DDoS': '#14b8a6',           // Teal
    'Data Leak': '#f97316',      // Koyu turuncu
    'General': '#6b7280'         // Gri
    // Default fallback: #6b7280
};

document.addEventListener('DOMContentLoaded', () => {
    fetchNews(1);
    updateStats();
    updateAIStatus();

    // Polling düzenekleri
    setInterval(updateAIStatus, 15000);   // AI durumunu ve kuyruğu 15sn'de bir çek
    setInterval(() => {
        // Eğer ilk sayfadaysak yeni haberleri kontrol et
        if (typeof currentPage !== 'undefined' && currentPage === 1) {
            fetchNews(1);
        }
        updateStats(); // Grafikleri güncelle
    }, 60000); // 1 dakikada bir veri yenile
});

async function updateSystemHealth() {
    try {
        const res = await fetch('/api/system/health');
        const data = await res.json();
        const cpuElem = document.getElementById('cpu-val');
        const ramElem = document.getElementById('ram-val');

        if (cpuElem) {
            cpuElem.innerText = `${data.cpu}%`;
            cpuElem.style.color = data.cpu > 80 ? '#ef4444' : '#3b82f6';
        }
        if (ramElem) {
            ramElem.innerText = `${data.ram}%`;
            ramElem.style.color = data.ram > 80 ? '#ef4444' : '#3b82f6';
        }

    } catch (e) { console.error("Sistem sağlık hatası:", e); }
}


async function updateAIStatus() {
    try {
        const res = await fetch('/api/ai_status');
        const data = await res.json();
        const bar = document.getElementById('ai-status-bar');
        if (!bar) return;

        let html = '<div style="display:flex; align-items:center; gap:12px; font-size:0.85rem; color:#90949a;"><b>AI ENGINE STATUS:</b>';
        for (const [provider, status] of Object.entries(data)) {
            if (provider === 'pending_analysis') continue;
            const isOnline = status === 'aktif' || status === 'active';
            const color = isOnline ? '#10b981' : '#f59e0b';
            html += `<span style="display:flex; align-items:center; gap:6px;">
                        <span style="width:8px; height:8px; border-radius:50%; background:${color}; box-shadow:0 0 8px ${color}"></span>
                        ${provider.toUpperCase()}
                     </span>`;
        }
        html += '</div>';

        // Kuyruk Durumu
        if (data.pending_analysis > 0) {
            html += `<div class="ai-badge pending" style="margin-left:auto; border: 1px solid #ef4444; background: rgba(239,68,68,0.1); padding: 2px 12px; border-radius: 20px; font-size: 0.8rem; color:#ef4444; font-weight:bold;">
                        ⏳ ${data.pending_analysis} News in Queue
                     </div>`;
        } else {
            html += `<div style="margin-left:auto; color: #3b82f6; font-size: 0.8rem; font-weight:500;">✨ All feeds analyzed</div>`;
        }

        // OTOMATİK GÜNCELLEME TETİKLEYİCİ: 
        // Eğer bekleyen sayısı azaldıysa (bir haber analiz edildiyse) sayfayı yenile
        if (lastPendingCount !== -1 && data.pending_analysis < lastPendingCount) {
            console.log("⚡ AI analizi tamamlandı, sayfa güncelleniyor...");
            if (currentPage === 1) fetchNews(1); // İlk sayfadaysak haberleri çek
            updateStats(); // Grafikleri güncelle
        }
        lastPendingCount = data.pending_analysis;

        bar.innerHTML = html;
        bar.style.display = 'flex';
        bar.style.alignItems = 'center';
        bar.style.width = '100%';
    } catch (e) { }
}



async function fetchNews(page = 1) {
    currentPage = page;
    const searchInput = document.getElementById('search-input');
    const search = searchInput ? searchInput.value : '';

    try {
        const res = await fetch(`/api/news?page=${page}&search=${encodeURIComponent(search)}`);
        const data = await res.json();
        renderNews(data.news);
        renderPagination(data.total, data.per_page, data.current_page);
    } catch (e) { console.error("Haber hatası:", e); }
}

function renderNews(newsItems) {
    const feed = document.getElementById('news-feed');
    if (!feed) return;
    feed.innerHTML = '';

    if (!newsItems || newsItems.length === 0) {
        feed.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #90949a;">📭 Henüz haber bulunamadı veya kriterlere uygun sonuç yok.</div>';
        return;
    }

    newsItems.forEach(item => {
        let level = (item.ai_analysis || "").includes('KRITIK') ? 'critical' :
            (item.ai_analysis || "").includes('ORTA') ? 'medium' : 'low';

        // Güvenli tırnak kaçırma
        const safeTitle = (item.title || "").replace(/'/g, "\\'").replace(/"/g, "&quot;");

        const category = item.category || 'General';
        const categoryColor = CATEGORY_COLORS[category] || CATEGORY_COLORS['General'];

        const card = document.createElement('div');
        card.className = `news-card ${level}`;
        card.innerHTML = `
            <div class="card-meta">
                <span class="threat-badge badge-${level}">${level.toUpperCase()}</span>
                <span class="category-badge" style="background: ${categoryColor}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; margin-left: 6px;">
                    ${category}
                </span>
                <small>${item.source}</small>
            </div>
            <h3>${item.title}</h3>
            <div class="card-actions">
                <a href="${item.link}" target="_blank" class="btn-link">🌐 Git</a>
                <button class="btn-analyze" onclick="analyzeNews('${safeTitle}', '${item.link}')">
                    ${item.ai_analysis ? '🧠 Ai Analizi' : '🧠 Analiz'}
                </button>
            </div>`;
        feed.appendChild(card);
    });
}

function searchNews(event) {
    // Esc tuşuna basılırsa aramayı temizle
    if (event.key === "Escape") {
        document.getElementById('search-input').value = "";
        fetchNews(1);
        return;
    }
    // Her tuş basımında değil, debounce yapılabilir ama şimdilik doğrudan çağırıyoruz
    fetchNews(1);
}

function renderPagination(total, perPage, current) {
    const container = document.getElementById('pagination-container');
    if (!container) return;
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
        if (barChart) barChart.destroy();
        barChart = new Chart(ctxBar, {
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

        // Her çubuk için renk ata
        const barColors = catLabels.map(label => CATEGORY_COLORS[label] || CATEGORY_COLORS['General']);

        categoryChart = new Chart(ctxCat, {
            type: 'bar',
            data: {
                labels: catLabels.map(l => l.length > 30 ? l.substring(0, 27) + "..." : l),
                datasets: [{
                    label: 'Olay Sayısı',
                    data: catCounts,
                    backgroundColor: barColors,
                    borderRadius: 6,
                    barThickness: 'flex',  // Otomatik genişlik
                    maxBarThickness: 40    // Maksimum genişlik sınırı
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                onClick: (event, elements) => {
                    // Çubuğa tıklandığında kategori filtreleme
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        const category = catLabels[index];
                        filterNewsByCategory(category);
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        enabled: true,
                        backgroundColor: 'rgba(21, 25, 30, 0.9)',
                        titleColor: '#3b82f6',
                        bodyColor: '#e1e1e1',
                        padding: 12,
                        cornerRadius: 8,
                        callbacks: {
                            label: function (context) {
                                return `${context.parsed.x} haber (Tıkla: Filtrele)`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        grid: { color: 'rgba(255,255,255,0.03)' },
                        ticks: { color: '#90949a', stepSize: 5 }
                    },
                    y: {
                        grid: { display: false },
                        ticks: {
                            color: '#e1e1e1',
                            font: { weight: '600', size: 11 },
                            padding: 8
                        }
                    }
                },
                layout: {
                    padding: {
                        left: 10,
                        right: 10,
                        top: 10,
                        bottom: 10
                    }
                }
            }
        });

    } catch (e) { console.error("Grafik hatası:", e); }

}

// Kategoriye göre haberleri filtrele
async function filterNewsByCategory(category) {
    try {
        // Arama inputunu temizle
        const searchInput = document.getElementById('search-input');
        if (searchInput) searchInput.value = '';

        // Kategori bilgisini göster
        const feed = document.getElementById('news-feed');
        feed.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 20px; color: #3b82f6;">
            🔍 <b>${category}</b> kategorisi yükleniyor...
        </div>`;

        // API'den kategori bazlı haberleri çek
        const res = await fetch(`/api/news?category=${encodeURIComponent(category)}&page=1`);
        const data = await res.json();

        if (data.news && data.news.length > 0) {
            renderNews(data.news);
            renderPagination(data.total, 10, 1);

            // Sayfayı haber akışına kaydır
            const feedElem = document.getElementById('feed');
            if (feedElem) feedElem.scrollIntoView({ behavior: 'smooth' });
        } else {
            feed.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #90949a;">
                📭 <b>${category}</b> kategorisinde haber bulunamadı.
            </div>`;
        }
    } catch (e) {
        console.error("Kategori filtreleme hatası:", e);
    }
}

async function queryDNS() {
    const input = document.getElementById('dns-input');
    const domain = input ? input.value.trim() : '';
    if (!domain) return alert("Lütfen bir domain girin");

    const panel = document.getElementById('analysis-panel');
    const display = document.getElementById('analysis-text');
    if (panel) panel.classList.remove('hidden');

    if (display) display.innerHTML = `🔍 <b>${domain}</b> DNS kayıtları sorgulanıyor...`;

    try {
        const res = await fetch(`/api/dns?domain=${domain}`);
        const data = await res.json();
        if (display) {
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
        }
    } catch (e) { if (display) display.innerHTML = "Sistem hatası oluştu."; }
}

async function queryWhois() {
    const input = document.getElementById('whois-input');
    const domain = input ? input.value.trim() : '';
    if (!domain) return alert("Lütfen bir domain girin");

    const panel = document.getElementById('analysis-panel');
    const display = document.getElementById('analysis-text');
    if (panel) panel.classList.remove('hidden');
    if (display) display.innerHTML = `🔍 <b>${domain}</b> WHOIS bilgileri çekiliyor...`;

    try {
        const res = await fetch(`/api/whois?domain=${domain}`);
        const data = await res.json();
        if (display) {
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
        }
    } catch (e) { if (display) display.innerHTML = "Sistem hatası oluştu."; }
}

async function analyzeNews(title, link) {
    const panel = document.getElementById('analysis-panel');
    const display = document.getElementById('analysis-text');
    if (panel) panel.classList.remove('hidden');
    if (display) display.innerText = "Analiz ediliyor...";

    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, link })
        });
        const data = await res.json();
        if (display) {
            display.innerText = data.analysis;
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
            display.appendChild(document.createElement('br'));
            display.appendChild(downloadBtn);
        }

        fetchNews(currentPage);

    } catch (e) { if (display) display.innerText = "Hata oluştu."; }
}

async function queryCVE() {
    const input = document.getElementById('cve-input');
    const cveId = input ? input.value.trim() : '';
    if (!cveId) return alert("Lütfen bir CVE ID girin (Örn: CVE-2024-1234)");

    const panel = document.getElementById('analysis-panel');
    const display = document.getElementById('analysis-text');

    if (panel) panel.classList.remove('hidden');
    if (display) display.innerHTML = `<div class="loading">🔍 <b>${cveId}</b> araştırılıyor ve AI analizi hazırlanıyor...</div>`;

    try {
        const res = await fetch(`/api/cve?id=${cveId}`);
        const data = await res.json();
        if (display) {
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
        }
    } catch (e) { if (display) display.innerHTML = "Sistem hatası oluştu."; }
}

async function queryIP() {
    const input = document.getElementById('ip-input');
    const ip = input ? input.value.trim() : '';
    if (!ip) return alert("Lütfen bir IP adresi girin");

    const panel = document.getElementById('analysis-panel');
    const display = document.getElementById('analysis-text');
    if (panel) panel.classList.remove('hidden');
    if (display) display.innerHTML = `🔍 <b>${ip}</b> sorgulanıyor...`;

    try {
        const res = await fetch(`/api/ip?ip=${ip}`);
        const data = await res.json();
        if (display) {
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
        }
    } catch (e) { if (display) display.innerHTML = "Sistem hatası oluştu."; }
}

function closeAnalysis() {
    const panel = document.getElementById('analysis-panel');
    if (panel) panel.classList.add('hidden');
}

function searchNews(e, page = 1) {
    if (e && e.type === 'keyup' && e.key !== 'Enter') return;
    fetchNews(page);
}

async function analyzeAll() {
    if (!confirm('Bekleyen tüm haberlerin toplu analizi başlatılsın mı? (Bu işlem arka planda yapılır)')) return;
    try {
        const res = await fetch('/api/analyze_all', { method: 'POST' });
        const data = await res.json();
        alert(data.message || data.error);
    } catch (e) { alert('İşlem başlatılamadı.'); }
}

async function querySubdomains() {
    const input = document.getElementById('subs-input');
    const domain = input ? input.value.trim() : '';
    if (!domain) return alert("Lütfen bir domain girin");

    const panel = document.getElementById('analysis-panel');
    const display = document.getElementById('analysis-text');
    if (panel) panel.classList.remove('hidden');
    if (display) display.innerHTML = `<div class="loading">📡 <b>${domain}</b> için pasif keşif yapılıyor (crt.sh)...</div>`;

    try {
        const res = await fetch(`/api/subdomains?domain=${domain}`);
        const data = await res.json();
        if (display) {
            if (data.error) {
                display.innerHTML = `<p style="color: #ef4444;">❌ Hata: ${data.error}</p>`;
            } else {
                display.innerHTML = `
                    <div class="subs-result">
                        <h4>Keşfedilen Subdomainler: ${data.domain}</h4>
                        <p><small>Sadece benzersiz ve ilk 50 kayıt listelenmiştir.</small></p>
                        <hr>
                        <div style="max-height: 400px; overflow-y: auto; text-align: left;">
                            <ul style="list-style: none; padding: 0;">
                                ${data.subdomains.map(s => `<li style="padding: 6px; border-bottom: 1px solid rgba(255,255,255,0.05); color: #3b82f6;">🔗 ${s}</li>`).join('')}
                            </ul>
                        </div>
                    </div>`;
            }
        }
    } catch (e) { if (display) display.innerHTML = "Sistem hatası oluştu."; }
}

async function updateSystemHealth() {
    try {
        const res = await fetch('/api/system/health');
        const data = await res.json();
        const cpuElem = document.getElementById('cpu-val');
        const ramElem = document.getElementById('ram-val');
        if (cpuElem) {
            cpuElem.innerText = `${data.cpu}%`;
            cpuElem.style.color = data.cpu > 80 ? '#ef4444' : '#3b82f6';
        }
        if (ramElem) {
            ramElem.innerText = `${data.ram}%`;
            ramElem.style.color = data.ram > 80 ? '#ef4444' : '#3b82f6';
        }
    } catch (e) { }
}

async function downloadWeeklyReport() {
    try {
        const res = await fetch('/api/news?page=1');
        const data = await res.json();
        let report = '# SentinelAi Haftalık Güvenlik Raporu\nOluşturulma: ' + new Date().toLocaleString() + '\n\n';

        data.news.forEach(item => {
            report += '### ' + item.title + '\n';
            report += '* **Kaynak:** ' + item.source + '\n';
            report += '* **Tarih:** ' + item.published + '\n';
            report += '* **Analiz:** ' + (item.ai_analysis || 'Henüz analiz edilmedi.') + '\n\n';
            report += '---\n\n';
        });

        const blob = new Blob([report], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'sentinel-haftalik-rapor-' + new Date().toISOString().split('T')[0] + '.md';
        a.click();
    } catch (e) { alert('Rapor oluşturulamadı.'); }
}
