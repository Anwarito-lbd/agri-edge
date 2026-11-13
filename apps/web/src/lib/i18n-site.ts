/**
 * English / French strings shared by the public site chrome that the design v2 JSON does not cover:
 * the footer links to the older pages and the footer safety line. The page copy itself (home, vision,
 * product, pricing, about, header, footer) lives in i18n-design.ts. Merged into the main dictionaries
 * in i18n.ts, so the same tests (every English key has a French one) cover them.
 *
 * Honesty rule for every string here: this is a software prototype, simulated and bench-tested.
 * No field-validation, customer, accuracy or revenue claims.
 */

export const siteEn = {
  "nav.site.proof": "Proof",
  "nav.site.hardware": "Hardware",
  "nav.site.companion": "Companion",
  "nav.site.dashboard": "Dashboard",
  "footer.github": "GitHub",
  "footer.legal": "Models are sensors, not decisions. Treatment requires validated_locally AND geofence. No spray capability ships with this product. The app does not fly the aircraft.",
} as const;

export type SiteKey = keyof typeof siteEn;

export const siteFr: Record<SiteKey, string> = {
  "nav.site.proof": "Preuves",
  "nav.site.hardware": "Matériel",
  "nav.site.companion": "Compagnon",
  "nav.site.dashboard": "Tableau de bord",
  "footer.github": "GitHub",
  "footer.legal": "Les modèles sont des capteurs, pas des décisions. Un traitement exige validated_locally ET une géoclôture. Aucune capacité de pulvérisation n’est livrée avec ce produit. L’application ne pilote pas l’aéronef.",
};
