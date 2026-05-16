/**
 * Po `vite build` synchronizuje názvy souborů s hashem do `app/web/index.html`.
 * Nemění default flag ani jinou logiku — pouze REACT_VEHICLE_LIST_BUILD_* a orientační komentář.
 * Při chybě (0 nebo >1 kandidát, chybějící soubory) končí exit 1 a index.html se nezapisuje.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootFrontend = path.resolve(__dirname, '..');
const assetsDir = path.join(rootFrontend, '../web/react/vehicle-list/assets');
const indexPath = path.join(rootFrontend, '../web/index.html');

function listIndexAssets(files) {
  const js = files.filter((f) => /^index-.+\.js$/.test(f));
  const css = files.filter((f) => /^index-.+\.css$/.test(f));
  return { js, css };
}

function main() {
  try {
    if (!fs.existsSync(assetsDir)) {
      throw new Error(`Složka neexistuje: ${assetsDir}`);
    }
    if (!fs.existsSync(indexPath)) {
      throw new Error(`Soubor neexistuje: ${indexPath}`);
    }

    const all = fs.readdirSync(assetsDir);
    const { js: jsFiles, css: cssFiles } = listIndexAssets(all);

    if (jsFiles.length !== 1) {
      throw new Error(
        `Očekáván právě jeden soubor index-*.js ve ${assetsDir}, nalezeno: ${jsFiles.length} (${jsFiles.join(', ') || '—'})`,
      );
    }
    if (cssFiles.length !== 1) {
      throw new Error(
        `Očekáván právě jeden soubor index-*.css ve ${assetsDir}, nalezeno: ${cssFiles.length} (${cssFiles.join(', ') || '—'})`,
      );
    }

    const buildJs = jsFiles[0];
    const buildCss = cssFiles[0];

    const before = fs.readFileSync(indexPath, 'utf8');

    if (!/var REACT_VEHICLE_LIST_BUILD_CSS = '[^']+';/.test(before)) {
      throw new Error('V index.html chybí řádek var REACT_VEHICLE_LIST_BUILD_CSS = \'...\';');
    }
    if (!/var REACT_VEHICLE_LIST_BUILD_JS = '[^']+';/.test(before)) {
      throw new Error('V index.html chybí řádek var REACT_VEHICLE_LIST_BUILD_JS = \'...\';');
    }

    let after = before.replace(
      /var REACT_VEHICLE_LIST_BUILD_CSS = '[^']*';/,
      `var REACT_VEHICLE_LIST_BUILD_CSS = '${buildCss}';`,
    );
    after = after.replace(
      /var REACT_VEHICLE_LIST_BUILD_JS = '[^']*';/,
      `var REACT_VEHICLE_LIST_BUILD_JS = '${buildJs}';`,
    );

    const commentRe = /(Aktuální build:\s*)index-[^,]+\.js, index-[^\n]+\.css/;
    if (commentRe.test(after)) {
      after = after.replace(commentRe, `$1${buildJs}, ${buildCss}`);
    }

    if (after === before) {
      console.log('[update-react-assets] index.html již odpovídá buildu, zápis přeskočen.');
      return;
    }

    fs.writeFileSync(indexPath, after, 'utf8');
    console.log(
      `[update-react-assets] OK: ${buildJs}, ${buildCss} → app/web/index.html`,
    );
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error('[update-react-assets] Chyba:', msg);
    process.exit(1);
  }
}

main();
