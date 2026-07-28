import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// Scraper réécrit SANS navigateur (ex-Puppeteer) : lotobonheur.ci est une
// page Next.js server-rendered (getServerSideProps), les résultats sont déjà
// dans le HTML au chargement (blob __NEXT_DATA__), et le sélecteur de mois du
// site appelle en interne une vraie route JSON : /api/results?monthYear=...
// (trouvée en inspectant le bundle client _next/static/chunks/pages/resultats-*.js).
// Un simple fetch() natif (Node 18+) sur cette API suffit donc — pas de JS à
// exécuter, pas de Chrome à installer, fonctionne dans n'importe quel sandbox
// éphémère sans dépendance navigateur.

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const RESULTS_FILE_PATH = path.join(__dirname, 'results.json');

const API_URL = 'https://lotobonheur.ci/api/results';
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

// dayText: "dimanche 26/07" — weekStartDate/weekEndDate: "20/07/2026"/"26/07/2026".
// Une semaine peut chevaucher deux mois (et exceptionnellement deux années,
// à la bascule décembre/janvier) : on déduit l'année en faisant correspondre
// le mois du jour avec celui du début ou de la fin de semaine.
function resolveDate(dayText, weekStartDate, weekEndDate) {
  const dayMonthMatch = dayText.match(/(\d{2})\/(\d{2})/);
  if (!dayMonthMatch) return null;
  const [, day, month] = dayMonthMatch;

  const startMatch = weekStartDate.match(/(\d{2})\/(\d{2})\/(\d{4})/);
  const endMatch = weekEndDate.match(/(\d{2})\/(\d{2})\/(\d{4})/);

  let year = null;
  if (startMatch && startMatch[2] === month) year = startMatch[3];
  else if (endMatch && endMatch[2] === month) year = endMatch[3];
  else if (endMatch) year = endMatch[3]; // repli raisonnable

  if (!year) return null;
  return `${year}-${month}-${day}`;
}

// "41 - 67 - 52 - 39 - 38" -> [41,67,52,39,38] ; "." = résultat pas encore tombé.
function parseNumbers(str) {
  if (!str) return [];
  const parts = str.split('-').map(s => s.trim());
  if (parts.some(p => !/^\d+$/.test(p))) return [];
  return parts.map(Number);
}

function extractRecords(apiData) {
  const records = [];
  for (const week of apiData.drawsResultsWeekly || []) {
    for (const day of week.drawResultsDaily || []) {
      const date = resolveDate(day.date, week.startDate, week.endDate);
      if (!date) continue;

      const allDraws = [
        ...(day.drawResults?.standardDraws || []),
        ...(day.drawResults?.nightDraws || []),
      ];

      for (const draw of allDraws) {
        if (!draw.drawName || draw.drawName === '-') continue;

        const winningNumbers = parseNumbers(draw.winningNumbers);
        const machineNumbers = parseNumbers(draw.machineNumbers);
        if (winningNumbers.length !== 5) continue; // tirage pas encore tombé / incomplet

        records.push({
          date,
          week: `${week.startDate} - ${week.endDate}`,
          day: day.date,
          game: draw.drawName,
          winningNumbers,
          machineNumbers,
        });
      }
    }
  }
  return records;
}

async function fetchMonth(monthYear) {
  const url = new URL(API_URL);
  if (monthYear) url.searchParams.set('monthYear', monthYear);
  url.searchParams.set('drawType', '');

  const res = await fetch(url, { headers: { 'User-Agent': USER_AGENT } });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} pour monthYear="${monthYear || '(courant)'}"`);
  }
  const data = await res.json();
  if (!data.success) {
    throw new Error(`Réponse API success=false pour monthYear="${monthYear || '(courant)'}"`);
  }
  return data;
}

async function main() {
  const args = process.argv.slice(2);
  const scrapeAll = args.includes('--all');
  const limitMonths = args.find(arg => arg.startsWith('--months='))
    ? parseInt(args.find(arg => arg.startsWith('--months=')).split('=')[1], 10)
    : null;

  console.log(`Starting Loto Bonheur scraper (fetch API, sans navigateur)... (scrapeAll: ${scrapeAll}, limitMonths: ${limitMonths || 'unset'})`);

  console.log('Récupération du mois courant...');
  const currentData = await fetchMonth('');
  let allScrapedData = extractRecords(currentData);
  console.log(`  ${allScrapedData.length} tirages récupérés (mois courant).`);

  let monthsToScrape = [];
  if (scrapeAll) {
    monthsToScrape = currentData.monthYears || [];
  } else if (limitMonths) {
    monthsToScrape = (currentData.monthYears || []).slice(0, limitMonths);
  }

  for (const monthYear of monthsToScrape) {
    console.log(`Scraping ${monthYear}...`);
    try {
      const data = await fetchMonth(monthYear);
      const records = extractRecords(data);
      console.log(`  ${records.length} tirages récupérés pour ${monthYear}.`);
      allScrapedData = allScrapedData.concat(records);
    } catch (err) {
      console.error(`  Erreur pour ${monthYear}: ${err.message}`);
    }
    // Throttle poli entre les requêtes.
    await new Promise(r => setTimeout(r, 300));
  }

  // Fusionne avec les résultats existants, dédupliqués par (date, jeu).
  let existingData = [];
  if (fs.existsSync(RESULTS_FILE_PATH)) {
    try {
      existingData = JSON.parse(fs.readFileSync(RESULTS_FILE_PATH, 'utf8'));
      console.log(`Loaded ${existingData.length} existing records from results.json`);
    } catch (err) {
      console.error('Error reading existing results.json:', err);
    }
  }

  const mergedMap = new Map();
  existingData.forEach(item => {
    const key = `${item.date || item.day}_${item.game}`;
    mergedMap.set(key, item);
  });
  allScrapedData.forEach(item => {
    const key = `${item.date || item.day}_${item.game}`;
    mergedMap.set(key, item);
  });

  const mergedData = Array.from(mergedMap.values());
  mergedData.sort((a, b) => {
    if (a.date && b.date) return b.date.localeCompare(a.date);
    return 0;
  });

  fs.writeFileSync(RESULTS_FILE_PATH, JSON.stringify(mergedData, null, 2), 'utf8');
  console.log(`Successfully saved ${mergedData.length} records to ${RESULTS_FILE_PATH}`);
}

main().catch(err => {
  console.error('Scraper execution error:', err);
  process.exitCode = 1;
});
