"""dashboard.py - Simple Flask dashboard with statistics charts."""
import logging
import os
from pathlib import Path

from flask import Flask, render_template_string, jsonify

from db import DB

logger = logging.getLogger(__name__)
app = Flask(__name__)

DB_PATH = os.getenv('DB_PATH', 'data/users.db')
_db = DB(DB_PATH)


def get_stats():
    """Aggregate statistics from the database."""
    stats = _db.get_stats()
    # Daily new users for the last 10 days
    import sqlite3
    daily = []
    if Path(DB_PATH).exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute('''
                    SELECT date(joined_at) as day, COUNT(*) as count
                    FROM users
                    WHERE joined_at >= date('now', '-10 days')
                    GROUP BY date(joined_at)
                    ORDER BY day
                ''').fetchall()
                daily = [{'day': r['day'], 'count': r['count']} for r in rows]
        except sqlite3.Error as e:
            logger.error(f'Dashboard daily stats error: {e}')

    return {
        'total_users': stats['total'],
        'banned': stats['banned'],
        'downloads': stats['downloads'],
        'recognizes': stats['recognizes'],
        'daily': daily,
    }


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>داشبورد whatsmusic-bot</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Vazirmatn', Tahoma, sans-serif; background: #0a0a1a; color: #e0e0e0; padding: 2rem; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { text-align: center; color: #00d4ff; margin-bottom: 2rem; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }
        .stat-card { background: #1a1a2e; padding: 1.5rem; border-radius: 16px; border: 1px solid #2a2a4a; text-align: center; }
        .stat-card .number { font-size: 2.5rem; font-weight: 700; color: #00d4ff; }
        .stat-card .label { color: #8892b0; margin-top: 0.5rem; }
        .chart-container { background: #1a1a2e; padding: 1.5rem; border-radius: 16px; border: 1px solid #2a2a4a; margin-top: 1.5rem; }
        canvas { max-height: 300px; }
        .footer { text-align: center; margin-top: 2rem; color: #8892b0; }
    </style>
</head>
<body>
<div class="container">
    <h1>📊 داشبورد whatsmusic-bot</h1>
    <div class="stats-grid" id="statsGrid"></div>
    <div class="chart-container">
        <canvas id="dailyChart"></canvas>
    </div>
    <div class="footer">به‌روزرسانی خودکار هر ۳۰ ثانیه</div>
</div>
<script>
    async function loadStats() {
        const res = await fetch('/api/stats');
        const data = await res.json();
        const grid = document.getElementById('statsGrid');
        grid.innerHTML = `
            <div class="stat-card"><div class="number">${data.total_users}</div><div class="label">👥 کاربران</div></div>
            <div class="stat-card"><div class="number">${data.downloads}</div><div class="label">📥 دانلودها</div></div>
            <div class="stat-card"><div class="number">${data.recognizes}</div><div class="label">🎵 تشخیص‌ها</div></div>
            <div class="stat-card"><div class="number">${data.banned}</div><div class="label">⛔ مسدودشده</div></div>
        `;
        const labels = data.daily.map(d => d.day);
        const values = data.daily.map(d => d.count);
        if (window.dailyChart) {
            window.dailyChart.data.labels = labels;
            window.dailyChart.data.datasets[0].data = values;
            window.dailyChart.update();
        } else {
            const ctx = document.getElementById('dailyChart').getContext('2d');
            window.dailyChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'کاربران جدید',
                        data: values,
                        backgroundColor: 'rgba(0, 212, 255, 0.6)',
                        borderColor: '#00d4ff',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { labels: { color: '#e0e0e0' } } },
                    scales: { y: { beginAtZero: true, ticks: { color: '#8892b0' } }, x: { ticks: { color: '#8892b0' } } }
                }
            });
        }
    }
    loadStats();
    setInterval(loadStats, 30000);
</script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/stats')
def stats_api():
    return jsonify(get_stats())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
