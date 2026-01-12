import { mkdir, copyFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const SOURCE_DIR = path.resolve(__dirname, "..", "..", "data", "out");
const DEST_DIR = path.resolve(__dirname, "..", "public", "data");

const FILES = [
  "selected_city_pois_llm_theme_labeled.json",
  "selected_city_pois_llm_season_labeled.json",
  "google_city_distances.json",
];

async function sync() {
  await mkdir(DEST_DIR, { recursive: true });
  await Promise.all(
    FILES.map(async (file) => {
      const from = path.join(SOURCE_DIR, file);
      const to = path.join(DEST_DIR, file);
      await copyFile(from, to);
    })
  );
  console.log(`Synced ${FILES.length} data files to ${DEST_DIR}`);
}

sync().catch((error) => {
  console.error("Failed to sync planner data:", error);
  process.exitCode = 1;
});
