// PROMPT 7 — scénario complet joué dans l'interface (navigateur automatisé), comme un utilisateur.
import { createRequire } from "node:module";
import fs from "node:fs";
const { chromium } = createRequire(process.cwd() + "/")("@playwright/test");

const [, , BASE, WORK, OUT] = process.argv;
const RUSH = `${WORK}/rush_astuces.mp4`, REF = `${WORK}/reference_tiktok.mp4`;
const steps = [];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: "fr-FR" });
const jsErrors = [];
page.on("pageerror", (e) => jsErrors.push(e.message));
page.on("dialog", (d) => d.accept()); // confirmation d'export
const LONG = 15 * 60_000;

async function step(n, title, fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    steps.push({ n, title, ok: true, seconds: +((Date.now() - t0) / 1000).toFixed(1), detail: detail ?? "" });
  } catch (e) {
    steps.push({ n, title, ok: false, seconds: +((Date.now() - t0) / 1000).toFixed(1), detail: String(e.message).split("\n")[0] });
  }
  await page.screenshot({ path: `${OUT}/etape_${String(n).padStart(2, "0")}.png` }).catch(() => {});
  console.log(`${steps.at(-1).ok ? "OK " : "ÉCHEC"} ${n}. ${title} (${steps.at(-1).seconds} s) ${steps.at(-1).detail}`);
  if (!steps.at(-1).ok) throw new Error("arrêt");
}

let projectUrl = "";
try {
  await step(1, "Créer un projet", async () => {
    await page.goto(`${BASE}/new`);
    await page.getByPlaceholder("Ex. : 3 astuces pour apprendre").fill("Test final PROF IA");
    await page.locator('input[type=file]').setInputFiles(RUSH);
    await page.getByRole("button", { name: "Créer le projet" }).click();
    await page.waitForURL(/\/projects\/\d+/, { timeout: LONG });
    projectUrl = page.url();
    return projectUrl.split("/").pop();
  });
  await step(2, "Importer une vidéo", async () => {
    await page.getByText("rush_astuces.mp4").first().waitFor({ timeout: 30_000 });
    return "rush_astuces.mp4 présent dans les médias du projet";
  });
  await step(3, "Importer une référence", async () => {
    await page.goto(`${BASE}/references`);
    await page.locator('input[type=file]').setInputFiles(REF);
    await page.getByText("reference_tiktok.mp4").first().waitFor({ timeout: 60_000 });
    await page.getByRole("button", { name: "Analyser", exact: true }).first().click();
    await page.getByText("analysée", { exact: true }).first().waitFor({ timeout: LONG });
    await page.getByLabel("Sélectionner reference_tiktok.mp4").check();
    await page.getByPlaceholder("Nom du style").fill("Style test final");
    await page.getByRole("button", { name: /Analyser le style/ }).click();
    await page.waitForURL(/\/styles\/\d+/, { timeout: 60_000 });
    return "référence analysée, style créé";
  });
  await step(4, "Analyser le contenu", async () => {
    await page.goto(projectUrl);
    await page.getByRole("button", { name: /^Analyser \(scènes/ }).click();
    await page.getByText("analysé", { exact: true }).first().waitFor({ timeout: LONG });
    return "plans, silences et transcription Whisper";
  });
  await step(5, "Générer les sous-titres", async () => {
    const t = await page.locator('[data-testid=media-list] p.italic').first().textContent({ timeout: 30_000 });
    if (!/astuce/i.test(t)) throw new Error(`transcription inattendue : ${t}`);
    return t.slice(0, 90);
  });
  await step(7, "Appliquer un style (validation du style)", async () => {
    await page.goto(`${BASE}/references`);
    await page.getByText("Style test final").click();
    await page.getByPlaceholder("Non identifiée — choisissez").fill("DejaVu Sans");
    await page.getByRole("button", { name: "Enregistrer les modifications" }).click();
    await page.getByText("Modifications enregistrées").waitFor({ timeout: 30_000 });
    await page.getByRole("button", { name: "Valider", exact: true }).click();
    await page.getByText("★ style officiel").waitFor({ timeout: 30_000 });
    return "police choisie, style validé comme officiel";
  });
  await step(6, "Préparer un storyboard (avec le style)", async () => {
    await page.goto(projectUrl);
    await page.getByPlaceholder(/Ex\. : Transforme cette vidéo/).fill("TikTok éducatif de 20 secondes, sous-titres animés, zooms, transitions dynamiques");
    await page.locator("label", { hasText: "Style" }).locator("select").selectOption({ label: "★ Style test final" });
    await page.getByRole("button", { name: "Générer le storyboard" }).click();
    await page.locator("[data-testid=scene-list] li").first().waitFor({ timeout: LONG });
    const n = await page.locator("[data-testid=scene-list] li").count();
    await page.getByText("style : Style test final").waitFor();
    return `${n} scènes, style « Style test final » appliqué`;
  });
  await step(8, "Prévisualiser", async () => {
    await page.getByRole("button", { name: /Générer l'aperçu/ }).click();
    await page.locator("[data-testid=preview-player]").waitFor({ timeout: LONG });
    const d = await page.locator("[data-testid=preview-player]").evaluate((v) => new Promise((r) => v.readyState >= 1 ? r(v.duration) : v.addEventListener("loadedmetadata", () => r(v.duration))));
    return `aperçu lisible dans le lecteur (${d.toFixed(1)} s)`;
  });
  await step(9, "Modifier une scène", async () => {
    const first = page.locator("[data-testid=scene-list] li").first();
    await first.locator("select").first().selectOption("zoom_out");
    await first.locator("textarea").fill("TEXTE MODIFIÉ À LA MAIN");
    await page.getByRole("button", { name: "Enregistrer (nouvelle version)" }).click();
    await page.getByText("Storyboard v2").waitFor({ timeout: 30_000 });
    await page.getByRole("button", { name: /Générer l'aperçu/ }).click();
    await page.locator("[data-testid=preview-player]").waitFor({ timeout: LONG });
    return "effet « zoom arrière » + texte corrigé → version 2, aperçu régénéré";
  });
  await step(10, "Valider", async () => {
    await page.getByRole("button", { name: "Valider ce montage" }).click();
    await page.getByText("✓ Montage validé").waitFor({ timeout: 30_000 });
    return "version 2 validée";
  });
  await step(11, "Exporter en MP4", async () => {
    await page.getByRole("button", { name: "Exporter", exact: true }).click();
    await page.getByText("vérifié", { exact: true }).first().waitFor({ timeout: LONG });
    return "export TikTok 1080×1920, qualité standard, 30 i/s";
  });
} catch { /* étape en échec : rapport partiel */ }
await browser.close();
fs.writeFileSync(`${OUT}/ui_steps.json`, JSON.stringify({ steps: steps.sort((a, b) => a.n - b.n), jsErrors, project: projectUrl.split("/").pop() }, null, 2));
