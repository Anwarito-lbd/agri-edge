import type { ReactNode } from "react";

/** The design's page header: H1, one line of context, and actions on the right. */
export function OpsPageHead({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children?: ReactNode;
}) {
  return (
    <div className="ph">
      <div>
        <h1>{title}</h1>
        {sub ? <p>{sub}</p> : null}
      </div>
      {children ? <div className="acts">{children}</div> : null}
    </div>
  );
}

/** READ-ONLY tag (lock icon + text; never colour alone). */
export function ReadOnlyTag({ label }: { label: string }) {
  return (
    <span className="ro">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="5" y="11" width="14" height="10" rx="2" />
        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      </svg>
      <span>{label}</span>
    </span>
  );
}

/** Small "demo" tag next to values that come from the built-in synthetic sample data. */
export function DemoTag({ label }: { label: string }) {
  return <span className="tag-demo">{label}</span>;
}
