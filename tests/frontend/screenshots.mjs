// Captures d'écran de chaque page de l'instance isolée (contrôle visuel du tableau de bord).
import { createRequire } from "node:module";
const { chromium } = createRequire(process.cwd() + "/")("@playwright/test");

const BASE = process.env.UI_URL ?? "http://localhost:3100";
const OUT = process.argv[2] ?? "screens";
const pid = process.argv[3] ?? "1";
const pages = [
  ["accueil", "/"], ["nouveau", "/new"], ["bibliotheque", "/library"], ["references", "/references"], ["personnages", "/characters"],
  ["storyboard", "/storyboard"], ["editeur", "/editor"], ["exports", "/exports"], ["projet", `/projects/${pid}`],
];
const browser = await chromium.launch();
const errors = [];
for (const [vw, vh, tag] of [[1440, 900, "pc"], [390, 844, "mobile"]]) {
  const page = await browser.newPage({ viewport: { width: vw, height: vh } });
  page.on("pageerror", (e) => errors.push(`${tag} ${page.url()} : ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${tag} ${page.url()} console : ${m.text()}`); });
  for (const [name, path] of pages) {
    if (tag === "mobile" && !["accueil", "projet"].includes(name)) continue;
    await page.goto(BASE + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(800);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    if (overflow) errors.push(`${tag} ${path} : défilement horizontal`);
    await page.screenshot({ path: `${OUT}/${tag}_${name}.png`, fullPage: name !== "projet" });
  }
  await page.close();
}
await browser.close();
console.log(errors.length ? "PROBLEMES:\n" + errors.join("\n") : "AUCUNE ERREUR JS");
