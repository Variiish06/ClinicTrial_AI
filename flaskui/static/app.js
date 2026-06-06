/* ═══════════════════════════════════════════════════════════════
   DeliriumWatch — Frontend Logic
   ═══════════════════════════════════════════════════════════════ */

// ─── THEME ──────────────────────────────────────────────────────
const rootEl = document.getElementById('htmlRoot');
const themeBtn = document.getElementById('themeToggle');
let isDark = localStorage.getItem('dw-dark') !== 'false'; // default dark
if (!isDark) setLight(); else setDark();

themeBtn.addEventListener('click', () => {
  isDark = !isDark;
  if (isDark) { setDark(); localStorage.setItem('dw-dark', 'true'); }
  else { setLight(); localStorage.setItem('dw-dark', 'false'); }
  renderCharts();
});

function setDark() {
  rootEl.setAttribute('data-bs-theme', 'dark');
  Chart.defaults.color = '#94a3b8';
  themeBtn.innerHTML = '<i class="fa-solid fa-sun text-warning"></i>';
}
function setLight() {
  rootEl.setAttribute('data-bs-theme', 'light');
  Chart.defaults.color = '#475569';
  themeBtn.innerHTML = '<i class="fa-solid fa-moon"></i>';
}

// ─── PRESETS ────────────────────────────────────────────────────
function loadPreset(presetId) {
  fetch(`/api/presets/${presetId}`)
    .then(r => r.json())
    .then(data => {
      const map = {
        'patient_name': 'inp_name', 'patient_bed': 'inp_bed',
        'patient_zone': 'inp_zone', 'gender_select': 'inp_gender',
        'age': 'inp_age', 'avg_sofa': 'inp_sofa', 'icu_select': 'inp_icu',
        'hr_mean': 'inp_hr', 'rr_mean': 'inp_rr', 'nibp_mean': 'inp_map',
        'spo2_min': 'inp_spo2', 'spo2_mean': 'inp_spo2m', 'abp_measured': 'inp_abp',
        'propofol_total': 'inp_prop', 'fentanyl_total': 'inp_fent',
        'midazolam_total': 'inp_midaz', 'lorazepam_total': 'inp_loraz',
        'nid_score': 'inp_nid',
      };
      for (const [key, elId] of Object.entries(map)) {
        const el = document.getElementById(elId);
        if (el && data[key] !== undefined) el.value = data[key];
      }
      // Hidden fields
      const hiddens = ['hr_std','rr_std','admission_sofa','unique_sedation_drugs'];
      hiddens.forEach(h => {
        const el = document.querySelector(`[name="${h}"]`);
        if (el && data[h] !== undefined) el.value = data[h];
      });
      // NID display
      const nidEl = document.getElementById('nidVal');
      if (nidEl && data.nid_score !== undefined) nidEl.textContent = data.nid_score;
    });
}

// ─── LOAD PATIENT FROM ROSTER ───────────────────────────────────
function loadPatient(p) {
  const el = (id) => document.getElementById(id);
  if (el('inp_name')) el('inp_name').value = p.name || '';
  if (el('inp_bed')) el('inp_bed').value = p.bed || '';
  if (el('inp_zone')) el('inp_zone').value = p.zone || 'Bay A';
  if (el('inp_gender')) el('inp_gender').value = p.gender || 'Male';
  if (p.values) {
    const valMap = {
      'age':'inp_age','avg_sofa':'inp_sofa','hr_mean':'inp_hr','rr_mean':'inp_rr',
      'nibp_mean':'inp_map','spo2_min':'inp_spo2','spo2_mean':'inp_spo2m',
      'abp_measured':'inp_abp','propofol_total':'inp_prop','fentanyl_total':'inp_fent',
      'midazolam_total':'inp_midaz','lorazepam_total':'inp_loraz','nid_score':'inp_nid'
    };
    for (const [k, id] of Object.entries(valMap)) {
      if (el(id) && p.values[k] !== undefined) el(id).value = p.values[k];
    }
    const nv = document.getElementById('nidVal');
    if (nv && p.values.nid_score !== undefined) nv.textContent = p.values.nid_score;
  }
  // Scroll to top on mobile
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ─── CHARTS ─────────────────────────────────────────────────────
let trendChart, shapChart;
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.weight = 500;

function renderCharts() {
  const dark = rootEl.getAttribute('data-bs-theme') === 'dark';
  const gridColor = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
  const textColor = dark ? '#94a3b8' : '#475569';

  // TREND CHART
  const probElem = document.getElementById('probData');
  let currentProb = 45;
  if (probElem) currentProb = parseFloat(probElem.textContent) * 100;

  const ctxTrend = document.getElementById('trendChart');
  if (ctxTrend) {
    let pts = [currentProb];
    let v = currentProb;
    for (let i = 0; i < 5; i++) {
      v = Math.max(5, Math.min(95, v + (Math.random() * 20 - 10)));
      pts.unshift(v);
    }
    if (trendChart) trendChart.destroy();
    trendChart = new Chart(ctxTrend, {
      type: 'line',
      data: {
        labels: ['48h', '36h', '24h', '12h', '6h', 'Now'],
        datasets: [{
          label: 'Risk %', data: pts,
          borderColor: '#6366f1',
          backgroundColor: dark ? 'rgba(99,102,241,0.15)' : 'rgba(99,102,241,0.1)',
          borderWidth: 2.5, fill: true, tension: 0.4,
          pointBackgroundColor: '#fff', pointBorderColor: '#6366f1',
          pointRadius: 4, pointHoverRadius: 7
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 } } },
          y: { grid: { color: gridColor }, min: 0, max: 100, ticks: { color: textColor, font: { size: 10 }, callback: v => v + '%' } }
        }
      }
    });
  }

  // SHAP CHART
  const shapElem = document.getElementById('shapData');
  if (shapElem && shapElem.textContent.trim() !== "[]") {
    try {
      const sData = JSON.parse(shapElem.textContent);
      if (sData.length > 0) {
        const labels = sData.map(d => d.name.toUpperCase().replace('_TOTAL', '').replace('ICU_', ''));
        const values = sData.map(d => d.value);
        const bgCols = values.map(v => v >= 0
          ? (dark ? 'rgba(239,68,68,0.7)' : 'rgba(239,68,68,0.8)')
          : (dark ? 'rgba(34,197,94,0.7)' : 'rgba(34,197,94,0.8)')
        );
        const ctxShap = document.getElementById('shapChart');
        if (ctxShap) {
          if (shapChart) shapChart.destroy();
          shapChart = new Chart(ctxShap, {
            type: 'bar',
            data: { labels, datasets: [{ data: values, backgroundColor: bgCols, borderRadius: 6 }] },
            options: {
              indexAxis: 'y', responsive: true, maintainAspectRatio: false,
              plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => `Shift: ${ctx.raw.toFixed(3)}` } }
              },
              scales: {
                x: { grid: { color: gridColor }, title: { display: true, text: 'Impact on Prediction', color: textColor, font: { size: 10 } } },
                y: { grid: { display: false }, ticks: { font: { size: 10, weight: 600 } } }
              }
            }
          });
        }
      }
    } catch (e) { /* silent */ }
  }
}

// ─── TELEMETRY ANIMATION ────────────────────────────────────────
const telCanvas = document.getElementById('telemetryCanvas');
if (telCanvas) {
  const tCtx = telCanvas.getContext('2d');
  const tW = telCanvas.offsetWidth || 900;
  const tH = telCanvas.offsetHeight || 100;
  telCanvas.width = tW * 2;
  telCanvas.height = tH * 2;
  tCtx.scale(2, 2);

  let offset = 0;
  const ecg = new Array(tW).fill(0);
  const eeg = new Array(tW).fill(0);

  function drawTelemetry() {
    tCtx.fillStyle = 'rgba(6,10,20,0.35)';
    tCtx.fillRect(0, 0, tW, tH);
    offset += 3;

    // ECG
    ecg.shift();
    if (Math.random() < 0.013) ecg.push(-25, 40, -12);
    else ecg.push((Math.random() - 0.5) * 2.5);

    // EEG
    eeg.shift();
    eeg.push(Math.sin(offset / 12) * 6 + Math.cos(offset / 20) * 4 + (Math.random() - 0.5) * 4);

    // Grid
    tCtx.strokeStyle = 'rgba(0,255,100,0.04)';
    tCtx.lineWidth = 0.5;
    tCtx.beginPath();
    for (let i = (offset * 2) % 40; i < tW; i += 40) { tCtx.moveTo(i, 0); tCtx.lineTo(i, tH); }
    tCtx.stroke();

    // ECG line
    tCtx.strokeStyle = '#00ff66';
    tCtx.lineWidth = 1.8;
    tCtx.beginPath();
    for (let i = 0; i < ecg.length; i++) tCtx.lineTo(i, tH / 3 - (ecg[i] || 0));
    tCtx.stroke();

    // EEG line
    tCtx.strokeStyle = '#06b6d4';
    tCtx.lineWidth = 1.2;
    tCtx.beginPath();
    for (let i = 0; i < eeg.length; i++) tCtx.lineTo(i, (tH / 3) * 2.2 - (eeg[i] || 0));
    tCtx.stroke();

    requestAnimationFrame(drawTelemetry);
  }
  drawTelemetry();
}

// ─── INIT ───────────────────────────────────────────────────────
renderCharts();
