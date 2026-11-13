/**
 * The public contact address.
 *
 * TODO(Anwar): no contact address exists anywhere in this repo, and one must
 * not be invented. Set NEXT_PUBLIC_CONTACT_EMAIL (Vercel -> Project -> Settings
 * -> Environment Variables, then redeploy) and every "Contact us" button turns
 * into a mailto: link. Until then they show a labelled placeholder.
 */
export const CONTACT_EMAIL: string = (process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "").trim();

export function contactHref(subject: string): string | null {
  if (!CONTACT_EMAIL) return null;
  return `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}`;
}
