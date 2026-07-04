import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const RESULTS_FILE_PATH = path.join(__dirname, 'results.json');

// Helper to parse date from dayText (e.g., "Vendredi 03/07") and weekText (e.g., "Semaine du 01/07/2026...")
function parseNormalizedDate(dayText, weekText) {
  try {
    const yearMatch = weekText.match(/\d{2}\/\d{2}\/(\d{4})/);
    const dayMonthMatch = dayText.match(/(\d{2})\/(\d{2})/);
    if (yearMatch && dayMonthMatch) {
      const year = yearMatch[1];
      const day = dayMonthMatch[1];
      const month = dayMonthMatch[2];
      return `${year}-${month}-${day}`;
    }
  } catch (e) {
    // Ignore and return null
  }
  return null;
}

async function scrapeMonth(page, monthValue) {
  console.log(`Scraping month: ${monthValue}...`);
  
  if (monthValue) {
    // Select the month in the dropdown
    await page.select('select#month', monthValue);
    // Wait for content rendering or network idle
    await new Promise(r => setTimeout(r, 4000));
  }

  const pageResults = await page.evaluate(() => {
    const data = [];
    const weekHeaders = Array.from(document.querySelectorAll('h4')).filter(h4 => 
      h4.innerText && h4.innerText.trim().startsWith('Semaine du')
    );

    weekHeaders.forEach(h4 => {
      const weekText = h4.innerText.trim();
      const parentContainer = h4.parentNode;

      // Find all day divs (which are div.pb-5 under the parent container, and siblings of h4)
      const dayDivs = Array.from(parentContainer.querySelectorAll('div.pb-5, div')).filter(el => {
        return el.parentNode === parentContainer && el.querySelector('h5');
      });

      dayDivs.forEach(dayDiv => {
        const h5 = dayDiv.querySelector('h5');
        const dayName = h5 ? h5.innerText.trim() : 'Unknown Day';

        const cards = dayDiv.querySelectorAll('div.flex.flex-col.space-y-2.bg-white');
        cards.forEach(card => {
          const gameNameEl = card.querySelector('div.font-bold, .text-sm.font-bold');
          const gameName = gameNameEl ? gameNameEl.innerText.trim() : 'Unknown Game';

          const rows = Array.from(card.querySelectorAll('div.flex.flex-row'));

          const gagnantsRow = rows.find(r => r.innerText.includes('Gagnants'));
          const winningNumbers = gagnantsRow 
            ? Array.from(gagnantsRow.querySelectorAll('.rounded-full, div.bg-green-700')).map(b => b.innerText.trim()).filter(n => n.length > 0)
            : [];

          const machineRow = rows.find(r => r.innerText.includes('Machine'));
          const machineNumbers = machineRow 
            ? Array.from(machineRow.querySelectorAll('.rounded-full, div.bg-green-700')).map(b => b.innerText.trim()).filter(n => n.length > 0)
            : [];

          data.push({
            weekText,
            dayText: dayName,
            gameName,
            winningNumbers,
            machineNumbers
          });
        });
      });
    });

    return data;
  });

  // Normalize dates on the Node side
  return pageResults.map(item => {
    const date = parseNormalizedDate(item.dayText, item.weekText);
    return {
      date,
      week: item.weekText,
      day: item.dayText,
      game: item.gameName,
      winningNumbers: item.winningNumbers.map(Number),
      machineNumbers: item.machineNumbers.map(Number)
    };
  });
}

async function main() {
  // Check command arguments
  const args = process.argv.slice(2);
  const scrapeAll = args.includes('--all');
  const limitMonths = args.find(arg => arg.startsWith('--months='))
    ? parseInt(args.find(arg => arg.startsWith('--months=')).split('=')[1], 10)
    : null;

  console.log(`Starting Loto Bonheur scraper... (scrapeAll: ${scrapeAll}, limitMonths: ${limitMonths || 'unset'})`);
  
  const browser = await puppeteer.launch({
    headless: "new",
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  try {
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    await page.setViewport({ width: 1280, height: 800 });

    console.log("Navigating to results page...");
    await page.goto('https://lotobonheur.ci/resultats', { waitUntil: 'networkidle2', timeout: 45000 });
    await new Promise(r => setTimeout(r, 4000));

    // Get available months in dropdown
    const availableMonths = await page.evaluate(() => {
      const select = document.querySelector('select#month');
      if (!select) return [];
      return Array.from(select.options)
        .map(opt => opt.value)
        .filter(val => val !== ""); // Exclude empty "Choisir..."
    });

    console.log(`Found ${availableMonths.length} historical months in dropdown.`);

    let monthsToScrape = [];
    if (scrapeAll) {
      monthsToScrape = availableMonths;
    } else if (limitMonths) {
      monthsToScrape = availableMonths.slice(0, limitMonths);
    } else {
      // Scrape current/default page results only
      monthsToScrape = [""]; 
    }

    let allScrapedData = [];

    for (const m of monthsToScrape) {
      const monthData = await scrapeMonth(page, m);
      console.log(`Scraped ${monthData.length} records for ${m || 'current month'}`);
      allScrapedData = allScrapedData.concat(monthData);
    }

    // Read existing results if any
    let existingData = [];
    if (fs.existsSync(RESULTS_FILE_PATH)) {
      try {
        existingData = JSON.parse(fs.readFileSync(RESULTS_FILE_PATH, 'utf8'));
        console.log(`Loaded ${existingData.length} existing records from results.json`);
      } catch (err) {
        console.error("Error reading existing results.json:", err);
      }
    }

    // Merge logic: avoid duplicate draws by comparing (date, game)
    const mergedMap = new Map();
    // Add existing
    existingData.forEach(item => {
      const key = `${item.date || item.day}_${item.game}`;
      mergedMap.set(key, item);
    });
    // Add newly scraped (overwrites or inserts)
    allScrapedData.forEach(item => {
      const key = `${item.date || item.day}_${item.game}`;
      mergedMap.set(key, item);
    });

    const mergedData = Array.from(mergedMap.values());
    
    // Sort by date descending, then game name
    mergedData.sort((a, b) => {
      if (a.date && b.date) {
        return b.date.localeCompare(a.date);
      }
      return 0;
    });

    fs.writeFileSync(RESULTS_FILE_PATH, JSON.stringify(mergedData, null, 2), 'utf8');
    console.log(`Successfully saved ${mergedData.length} records to ${RESULTS_FILE_PATH}`);

  } catch (error) {
    console.error("Scraper execution error:", error);
  } finally {
    await browser.close();
    console.log("Browser closed.");
  }
}

main();
