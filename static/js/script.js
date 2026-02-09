let currentPage = 1;
let currentAnalysisTitle = "";
let sourceChart = null;
let barChart = null;

document.addEventListener('DOMContentLoaded', () => {
    fetchNews(1);
    updateStats();
    document.addEventListener('keydown', (e) => { if(e.key === "Escape") closeAnalysis(); });
});

async function updateStats() {
    const res = await fetch('/api/stats');
    const data = await res.json();
    const labels = data.sources.map(s => s.source);
    const counts = data.sources.map(s => s.count);

    // Doughnut Chart
    const ctx1 = document.getElementById('sourceChart').getContext('2d');
    if(sourceChart) sourceChart.destroy();
    sourceChart = new Chart(ctx1, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: counts, backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'], borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: '#90949a', font: { size: 10 } } } } }
    });

    // Bar Chart
    const ctx2 = document.getElementById('barChart').getContext('2d');
    if(barChart) barChart.destroy();
    barChart = new Chart(ctx2, {
        type: 'bar',
        data: { labels, datasets: [{ label: 'Haber Sayısı', data: counts, backgroundColor: '#3b82f6' }] },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { ticks: { color: '#90949a' } }, x: { ticks: { color: '#90949a' } } } }
    });
}

async function fetchNews(page = 1) {
    currentPage = page;
    const query = document.getElementById('search-input').value;
    const res = await fetch(`/api/news?page=${page}&search=${encodeURIComponent(query)}`);
    const news = await res.json();
    renderNews(news);
    renderPagination(news.length);
}

function renderNews(news) {
    const feed = document.getElementById('news-feed');
    feed.innerHTML = '';
    news.forEach(item => {
        const card = document.createElement('div');
        card.className = 'news-card';
        card.innerHTML = `
            <div class="card-meta"><small>${item.source} • ${item.published}</small></div>
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

function renderPagination(count) {
    const container = document.getElementById('pagination-container');
    container.innerHTML = '';
    for(let i=1; i<=5; i++) {
        const btn = document.createElement('button');
        btn.innerText = i;
        if(i === currentPage) btn.className = 'active';
        btn.onclick = () => fetchNews(i);
        container.appendChild(btn);
    }
}

// Arşiv veya Analiz butonuna basıldığında tetiklenen ana fonksiyon
async function analyzeNews(title, link) {
    currentAnalysisTitle = title;
    openPanel("Analiz detayları hazırlanıyor..."); // Butona basıldığı an panel açılır
    
    try {
        const res = await fetch('/api/analyze', { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'}, 
            body: JSON.stringify({ title, link }) 
        });
        const data = await res.json();
        document.getElementById('analysis-text').innerText = data.analysis;
    } catch (e) {
        document.getElementById('analysis-text').innerText = "Analiz yüklenirken bir hata oluştu.";
    }
}

async function downloadSingleReport() {
    const content = document.getElementById('analysis-text').innerText;
    const response = await fetch('/api/report/single', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ title: currentAnalysisTitle, content }) });
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `Analiz.pdf`; a.click();
}

// Paneli açan ve içeriği yükleyen fonksiyon
function openPanel(msg) {
    const panel = document.getElementById('analysis-panel');
    panel.classList.remove('hidden'); // Gizli sınıfı kaldırır
    document.getElementById('analysis-text').innerText = msg;
}

// Paneli kapatan fonksiyon
function closeAnalysis() {
    const panel = document.getElementById('analysis-panel');
    panel.classList.add('hidden'); // Gizli sınıfı geri ekler
}

function searchNews() { fetchNews(1); }
function downloadWeeklyReport() { window.location.href = '/api/report/weekly'; }
