/**
 * English / French strings for the farmer-facing and ops screens.
 *
 * Canada is bilingual, and a Quebec or Manitoba francophone farm should not
 * have to run its operation in its second language. Every English key must
 * have a French one; tests/i18n.test.ts fails otherwise. `{name}` placeholders
 * are filled by `translate`.
 *
 * The dictionary is split across four files to keep each readable: this one
 * (login, recommendations, alerts, fields, prescriptions, map), i18n-ops.ts
 * (overview, live, weather, sensors), i18n-site.ts (header, footer, shared site strings)
 * and i18n-design.ts (the design v2 strings, keys "d.k…").
 */

import { designEn, designFr } from "@/lib/i18n-design";
import { opsEn, opsFr } from "@/lib/i18n-ops";
import { siteEn, siteFr } from "@/lib/i18n-site";

export type Lang = "en" | "fr";
export const LANGS: Lang[] = ["en", "fr"];
export const LANG_COOKIE = "lang";

const coreEn = {
  "lang.toggle": "Français",
  "lang.name": "English",

  "nav.overview": "Overview",
  "nav.recommendations": "Recommendations",
  "nav.map": "Map",
  "nav.fields": "Fields",
  "nav.prescriptions": "Prescriptions",
  "nav.live": "Live",
  "nav.weather": "Weather",
  "nav.sensors": "Sensors",
  "nav.alerts": "Alerts",

  "shell.title": "Operations Station",
  "shell.subtitle": "weather · soil · alerts · recommendations · map",
  "shell.simulation": "SIMULATION — synthetic demo data. Not live farm telemetry.",
  "shell.demo": "DEMO MODE — simulated sample data, no live farm connected.",
  "shell.live": "A connected ops station is answering. This prototype is not field-validated.",
  "shell.unreachable": "Ops station unreachable — nothing shown here is invented.",
  "shell.offlineCached": "Offline — showing data saved at {time}. Changes cannot be sent until the connection is back.",
  "shell.loggedInAs": "{name} · {role}",
  "shell.logout": "Log out",
  "shell.login": "Log in",

  "common.refresh": "Refresh",
  "common.loading": "Loading…",
  "common.none": "Nothing yet.",
  "common.error": "Something went wrong: {error}",
  "common.forbidden": "Your role cannot do this ({error}).",
  "common.save": "Save",
  "common.demo": "demo",

  "login.title": "Log in",
  "login.username": "Username",
  "login.password": "Password",
  "login.submit": "Log in",
  "login.failed": "Wrong username or password.",
  "login.locked": "Too many attempts. Wait a minute and try again.",
  "login.unreachable": "The ops station cannot be reached.",
  "login.note": "Accounts are created on the ops station by its administrator.",

  "rec.title": "Recommendations",
  "rec.intro": "Decision support, not decisions. Each item says why, what it could not see, and what its data rests on.",
  "rec.p1": "Act now",
  "rec.p2": "This week",
  "rec.p3": "For information",
  "rec.why": "Why",
  "rec.notKnown": "Not known",
  "rec.confidence": "Confidence: {level}",
  "rec.sources": "Data: {sources}",
  "rec.empty": "No recommendations. Add a field with its crop, seeding date and soil to get them.",
  "rec.showOnMap": "Show on map",

  "alerts.title": "Alerts",
  "alerts.severity": "Severity",
  "alerts.alert": "Alert",
  "alerts.state": "State",
  "alerts.category": "Category",
  "alerts.action": "Action",
  "alerts.ack": "Acknowledge",
  "alerts.resolve": "Resolve",
  "alerts.escalate": "Escalate",
  "alerts.done": "{action}: {id}",
  "alerts.by": "by {name}",
  "alerts.empty": "No alerts.",

  "fields.title": "Fields",
  "fields.intro": "Each field's crop, seeding date and soil drive its water balance, growth stage and disease risk.",
  "fields.id": "Field ID",
  "fields.name": "Name",
  "fields.crop": "Crop",
  "fields.seeded": "Seeded",
  "fields.soil": "Soil",
  "fields.lat": "Latitude",
  "fields.lon": "Longitude",
  "fields.irrigated": "Irrigated",
  "fields.boundary": "Boundary (GeoJSON Polygon, optional — needed for satellite and prescriptions)",
  "fields.add": "Add or update field",
  "fields.saved": "Saved {id}.",
  "fields.empty": "No fields yet.",
  "fields.satellite": "Satellite",
  "fields.refresh": "Refresh satellite",
  "fields.refreshStarted": "Satellite update started for {id}.",

  "rx.title": "Prescriptions",
  "rx.intro": "Maps your sprayer or spreader loads. Built from detections (spot spray) or satellite zones (variable rate); approved by an agronomist with a measured wind; then downloaded.",
  "rx.build": "Build",
  "rx.source": "Source",
  "rx.sourceDetections": "Detections (spot spray)",
  "rx.sourceSatellite": "Satellite zones (variable rate)",
  "rx.rate": "Rate",
  "rx.rates": "Rates by zone, low to high value (comma-separated)",
  "rx.product": "Product",
  "rx.unit": "Unit",
  "rx.field": "Field",
  "rx.cellsOn": "Cells on",
  "rx.treated": "Treated ha",
  "rx.total": "Total product",
  "rx.status": "Status",
  "rx.validated": "Validated",
  "rx.notValidated": "Not approvable",
  "rx.approved": "Approved by {name}",
  "rx.wind": "Measured wind now (m/s)",
  "rx.approve": "Approve",
  "rx.download": "Download",
  "rx.issues": "Why it cannot be approved",
  "rx.empty": "No prescriptions yet.",

  "map.title": "Map",
  "map.layers": "Layers",
  "map.fields": "Fields",
  "map.detections": "Detections",
  "map.satellite": "Satellite: declining patches",
  "map.prescription": "Prescription",
  "map.list": "Features on the map (list view)",
  "map.selectField": "Field for satellite layer",
  "map.tilesDown": "Basemap tiles could not be loaded. Features are shown on a plain background.",

  "offline.title": "You are offline",
  "offline.body": "The last data this device saved is shown. Anything you change is not sent until the connection is back.",
} as const;

/** Every English string: the screens people work in, the ops pages, and the public site. */
export const en = { ...coreEn, ...opsEn, ...siteEn, ...designEn } as const;

export type Key = keyof typeof en;

const coreFr: Record<keyof typeof coreEn, string> = {
  "lang.toggle": "English",
  "lang.name": "Français",

  "nav.overview": "Aperçu",
  "nav.recommendations": "Recommandations",
  "nav.map": "Carte",
  "nav.fields": "Champs",
  "nav.prescriptions": "Prescriptions",
  "nav.live": "Direct",
  "nav.weather": "Météo",
  "nav.sensors": "Capteurs",
  "nav.alerts": "Alertes",

  "shell.title": "Poste d’exploitation",
  "shell.subtitle": "météo · sol · alertes · recommandations · carte",
  "shell.simulation": "SIMULATION — données de démonstration synthétiques. Pas la télémétrie réelle de la ferme.",
  "shell.demo": "MODE DÉMO — données d’exemple simulées, aucune ferme réelle n’est connectée.",
  "shell.live": "Un poste d’exploitation connecté répond. Ce prototype n’est pas validé sur le terrain.",
  "shell.unreachable": "Poste d’exploitation injoignable — rien de ce qui est affiché n’est inventé.",
  "shell.offlineCached": "Hors ligne — données enregistrées à {time}. Les modifications ne peuvent pas être envoyées avant le retour de la connexion.",
  "shell.loggedInAs": "{name} · {role}",
  "shell.logout": "Se déconnecter",
  "shell.login": "Se connecter",

  "common.refresh": "Actualiser",
  "common.loading": "Chargement…",
  "common.none": "Rien pour l’instant.",
  "common.error": "Un problème est survenu : {error}",
  "common.forbidden": "Votre rôle ne permet pas cette action ({error}).",
  "common.save": "Enregistrer",
  "common.demo": "démo",

  "login.title": "Connexion",
  "login.username": "Nom d’utilisateur",
  "login.password": "Mot de passe",
  "login.submit": "Se connecter",
  "login.failed": "Nom d’utilisateur ou mot de passe incorrect.",
  "login.locked": "Trop de tentatives. Attendez une minute puis réessayez.",
  "login.unreachable": "Le poste d’exploitation est injoignable.",
  "login.note": "Les comptes sont créés sur le poste d’exploitation par son administrateur.",

  "rec.title": "Recommandations",
  "rec.intro": "Aide à la décision, pas des décisions. Chaque élément indique pourquoi, ce qu’il n’a pas pu voir et sur quelles données il repose.",
  "rec.p1": "À faire maintenant",
  "rec.p2": "Cette semaine",
  "rec.p3": "Pour information",
  "rec.why": "Pourquoi",
  "rec.notKnown": "Inconnu",
  "rec.confidence": "Confiance : {level}",
  "rec.sources": "Données : {sources}",
  "rec.empty": "Aucune recommandation. Ajoutez un champ avec sa culture, sa date de semis et son sol pour en obtenir.",
  "rec.showOnMap": "Voir sur la carte",

  "alerts.title": "Alertes",
  "alerts.severity": "Gravité",
  "alerts.alert": "Alerte",
  "alerts.state": "État",
  "alerts.category": "Catégorie",
  "alerts.action": "Action",
  "alerts.ack": "Prendre en charge",
  "alerts.resolve": "Résoudre",
  "alerts.escalate": "Escalader",
  "alerts.done": "{action} : {id}",
  "alerts.by": "par {name}",
  "alerts.empty": "Aucune alerte.",

  "fields.title": "Champs",
  "fields.intro": "La culture, la date de semis et le sol de chaque champ déterminent son bilan hydrique, son stade de croissance et son risque de maladie.",
  "fields.id": "Identifiant du champ",
  "fields.name": "Nom",
  "fields.crop": "Culture",
  "fields.seeded": "Semé le",
  "fields.soil": "Sol",
  "fields.lat": "Latitude",
  "fields.lon": "Longitude",
  "fields.irrigated": "Irrigué",
  "fields.boundary": "Limite (polygone GeoJSON, facultatif — requis pour le satellite et les prescriptions)",
  "fields.add": "Ajouter ou modifier le champ",
  "fields.saved": "{id} enregistré.",
  "fields.empty": "Aucun champ pour l’instant.",
  "fields.satellite": "Satellite",
  "fields.refresh": "Actualiser le satellite",
  "fields.refreshStarted": "Mise à jour satellite lancée pour {id}.",

  "rx.title": "Prescriptions",
  "rx.intro": "Cartes que votre pulvérisateur ou épandeur charge. Construites à partir des détections (pulvérisation localisée) ou des zones satellite (dose variable); approuvées par un agronome avec un vent mesuré; puis téléchargées.",
  "rx.build": "Construire",
  "rx.source": "Source",
  "rx.sourceDetections": "Détections (pulvérisation localisée)",
  "rx.sourceSatellite": "Zones satellite (dose variable)",
  "rx.rate": "Dose",
  "rx.rates": "Doses par zone, de la valeur la plus basse à la plus haute (séparées par des virgules)",
  "rx.product": "Produit",
  "rx.unit": "Unité",
  "rx.field": "Champ",
  "rx.cellsOn": "Cellules actives",
  "rx.treated": "ha traités",
  "rx.total": "Produit total",
  "rx.status": "Statut",
  "rx.validated": "Validée",
  "rx.notValidated": "Non approuvable",
  "rx.approved": "Approuvée par {name}",
  "rx.wind": "Vent mesuré maintenant (m/s)",
  "rx.approve": "Approuver",
  "rx.download": "Télécharger",
  "rx.issues": "Pourquoi elle ne peut pas être approuvée",
  "rx.empty": "Aucune prescription pour l’instant.",

  "map.title": "Carte",
  "map.layers": "Couches",
  "map.fields": "Champs",
  "map.detections": "Détections",
  "map.satellite": "Satellite : zones en déclin",
  "map.prescription": "Prescription",
  "map.list": "Éléments sur la carte (vue en liste)",
  "map.selectField": "Champ pour la couche satellite",
  "map.tilesDown": "Les tuiles du fond de carte n’ont pas pu être chargées. Les éléments sont affichés sur un fond uni.",

  "offline.title": "Vous êtes hors ligne",
  "offline.body": "Les dernières données enregistrées sur cet appareil sont affichées. Rien de ce que vous modifiez n’est envoyé avant le retour de la connexion.",
};

export const fr: Record<Key, string> = { ...coreFr, ...opsFr, ...siteFr, ...designFr };

const DICTS: Record<Lang, Record<Key, string>> = { en, fr };

export function translate(lang: Lang, key: Key, vars?: Record<string, string | number>): string {
  const s = DICTS[lang][key] ?? en[key];
  return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : s;
}

export function parseLang(value: string | undefined | null): Lang | undefined {
  return value === "fr" || value === "en" ? value : undefined;
}
