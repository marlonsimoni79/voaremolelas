const REFRESH_MS = 5 * 60 * 1000;
let windChart = null;
let rainChart = null;

const SOURCE_LABELS = {
  metar: "METAR (Allmetsat)",
  wunderground: "Wunderground (IPEROP1)",
  windguru: "Windguru",
};

const STATION_KEY = "pws-station";
const stationSelect = document.getElementById("station");

function compass(deg) {
  if (deg == null) return "?";
  const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return dirs[Math.round(deg / 22.5) % 16];
}

function fmt(value, unit, digits = 1) {
  if (value == null) return "—";
  return `${Number(value).toFixed(digits)}${unit ? " " + unit : ""}`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}

function renderVerdict(assessment) {
  const el = document.getElementById("verdict");
  const text = document.getElementById("verdict-text");
  const updated = document.getElementById("verdict-updated");
  el.classList.remove("good", "bad", "loading");
  if (assessment.verdict === "GOOD") {
    el.classList.add("good");
    text.textContent = "GOOD";
  } else {
    el.classList.add("bad");
    text.textContent = "BAD";
  }
  updated.textContent = `Assessed at ${fmtTime(assessment.assessed_at)}`;
}

function renderErrors(errors) {
  const el = document.getElementById("errors");
  if (!errors || errors.length === 0) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = `<strong>Data problems:</strong> ${errors.map((e) => `<div>${e}</div>`).join("")}`;
}

function renderCriteria(criteria) {
  const ul = document.getElementById("criteria");
  ul.innerHTML = "";
  for (const c of criteria) {
    const li = document.createElement("li");
    const badge = document.createElement("span");
    badge.className = `badge ${c.ok ? "ok" : "fail"}`;
    badge.textContent = c.ok ? "✓" : "✗";
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = c.label;
    const detail = document.createElement("span");
    detail.className = "detail";
    detail.textContent = c.detail;
    li.append(badge, label, detail);
    ul.appendChild(li);
  }
}

function renderSource(current) {
  const el = document.getElementById("source");
  if (!current || !current.source) {
    el.textContent = "";
    return;
  }
  const station = stationSelect ? stationSelect.value : "";
  const label = station
    ? `Wunderground (${station})`
    : SOURCE_LABELS[current.source] || current.source;
  el.textContent = `Weather source: ${label} · Rain: Open-Meteo`;
}

function renderCurrent(current, rainNow) {
  const el = document.getElementById("current");
  el.innerHTML = "";
  if (!current) {
    el.innerHTML = `<p class="hint">No station data available.</p>`;
    return;
  }
  const items = [
    {
      name: "Wind (avg)",
      value: fmt(current.wind_avg_kmh, "km/h"),
      arrow: current.wind_direction_deg,
    },
    { name: "Wind (max)", value: fmt(current.wind_max_kmh, "km/h") },
    {
      name: "Direction",
      value: current.wind_direction_deg == null ? "—" : `${Math.round(current.wind_direction_deg)}° ${compass(current.wind_direction_deg)}`,
    },
    { name: "Temperature", value: fmt(current.temperature_c, "°C") },
    { name: "Humidity", value: current.relative_humidity_pct == null ? "—" : `${current.relative_humidity_pct}%` },
    { name: "Pressure", value: fmt(current.mslp_hpa, "hPa") },
    {
      name: "Rain now",
      value: rainNow ? (rainNow.is_raining ? `${fmt(rainNow.rain_mm, "mm")}` : "dry") : "—",
    },
    {
      name: "Rain probability",
      value: rainNow && rainNow.precipitation_probability_pct != null ? `${rainNow.precipitation_probability_pct}%` : "—",
    },
  ];
  for (const item of items) {
    const div = document.createElement("div");
    div.className = "metric";
    const value = document.createElement("div");
    value.className = "value";
    if (item.arrow != null) {
      const arrow = document.createElement("span");
      arrow.className = "arrow";
      arrow.textContent = "↑";
      arrow.style.transform = `rotate(${item.arrow + 180}deg)`;
      value.appendChild(arrow);
      value.appendChild(document.createTextNode(" " + item.value));
    } else {
      value.textContent = item.value;
    }
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = item.name;
    div.append(value, name);
    el.appendChild(div);
  }
}

function renderWindChart(series) {
  const ctx = document.getElementById("wind-chart").getContext("2d");
  if (windChart) windChart.destroy();
  if (!series || !series.points || series.points.length === 0) {
    return;
  }
  const labels = series.points.map((p) => p.time ? new Date(p.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "");
  windChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Avg wind (km/h)",
          data: series.points.map((p) => p.wind_avg_kmh),
          borderColor: "#38bdf8",
          backgroundColor: "rgba(56, 189, 248, 0.15)",
          fill: true,
          tension: 0.3,
        },
        {
          label: "Max wind (km/h)",
          data: series.points.map((p) => p.wind_max_kmh),
          borderColor: "#f59e0b",
          borderDash: [5, 5],
          tension: 0.3,
        },
        {
          label: "Direction (deg)",
          data: series.points.map((p) => p.wind_direction_deg),
          borderColor: "#a78bfa",
          borderDash: [2, 4],
          yAxisID: "y1",
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "km/h" } },
        y1: { position: "right", min: 0, max: 360, grid: { drawOnChartArea: false }, title: { display: true, text: "deg" } },
      },
    },
  });
}

function renderRainChart(rainForecast) {
  const ctx = document.getElementById("rain-chart").getContext("2d");
  if (rainChart) rainChart.destroy();
  if (!rainForecast || !rainForecast.hours || rainForecast.hours.length === 0) {
    return;
  }
  const labels = rainForecast.hours.map((h) => h.slice(11, 16));
  rainChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Rain (mm)",
          data: rainForecast.rain_mm,
          backgroundColor: "rgba(56, 189, 248, 0.6)",
          yAxisID: "y",
        },
        {
          label: "Probability (%)",
          data: rainForecast.precipitation_probability_pct,
          type: "line",
          borderColor: "#ef4444",
          yAxisID: "y1",
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "mm" } },
        y1: { position: "right", min: 0, max: 100, grid: { drawOnChartArea: false }, title: { display: true, text: "%" } },
      },
    },
  });
}

function renderTephigrams(tephigrams) {
  const el = document.getElementById("tephigrams");
  el.innerHTML = "";
  if (!tephigrams || tephigrams.length === 0) {
    el.innerHTML = `<p class="hint">No tephigram data available.</p>`;
    return;
  }
  const sorted = [...tephigrams].sort((a, b) => (a.kind === b.kind ? 0 : a.kind === "observation" ? -1 : 1));
  for (const t of sorted) {
    const div = document.createElement("div");
    div.className = "tephigram";
    const img = document.createElement("img");
    img.src = t.url;
    img.alt = `Tephigram ${t.station_name} ${t.label}`;
    img.loading = "lazy";
    const caption = document.createElement("div");
    caption.className = "caption";
    caption.textContent = `${t.station_name} — ${t.kind} ${t.label}`;
    div.append(img, caption);
    el.appendChild(div);
  }
}

async function refresh() {
  try {
    const station = stationSelect ? stationSelect.value : "";
    const url = station
      ? `/api/weather?station=${encodeURIComponent(station)}`
      : "/api/weather";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderVerdict(data.assessment);
    renderErrors(data.assessment.errors);
    renderCriteria(data.assessment.criteria);
    renderSource(data.current);
    renderCurrent(data.current, data.rain_now);
    renderWindChart(data.series);
    renderRainChart(data.rain_forecast);
    renderTephigrams(data.tephigrams);
  } catch (err) {
    const el = document.getElementById("verdict");
    el.classList.remove("good", "bad");
    el.classList.add("loading");
    document.getElementById("verdict-text").textContent = "Failed to load data";
    document.getElementById("verdict-updated").textContent = String(err);
  }
}

if (stationSelect) {
  const saved = localStorage.getItem(STATION_KEY);
  if (saved) stationSelect.value = saved;
  stationSelect.addEventListener("change", () => {
    localStorage.setItem(STATION_KEY, stationSelect.value);
    refresh();
  });
}

refresh();
setInterval(refresh, REFRESH_MS);
