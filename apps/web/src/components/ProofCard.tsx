import Image from "next/image";
import type { ProofItem } from "@/lib/proof";

export function ProofCard({
  item,
  dense = false,
}: {
  item: ProofItem;
  dense?: boolean;
}) {
  return (
    <figure className="card overflow-hidden bg-white">
      <div
        className={`relative bg-surface ${
          dense ? "aspect-[16/10] sm:aspect-[5/3]" : "aspect-[4/3]"
        }`}
      >
        <Image
          src={item.src}
          alt={item.title}
          fill
          className={
            item.category === "physics" && !item.src.includes("hero")
              ? "object-contain bg-white p-1.5"
              : dense
                ? "object-cover"
                : "object-contain p-3"
          }
          sizes="(max-width: 768px) 100vw, 50vw"
        />
      </div>
      <figcaption
        className={`space-y-1 border-t border-border ${
          dense ? "px-3.5 py-3" : "px-4 py-4 space-y-1.5"
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <p className="eyebrow">{item.category}</p>
          {dense ? (
            <span className="text-[10px] font-medium uppercase tracking-wide text-muted">
              Evidence
            </span>
          ) : null}
        </div>
        <p className={`font-semibold text-ink ${dense ? "text-[13px]" : "text-sm"}`}>
          {item.title}
        </p>
        <p
          className={`leading-relaxed text-muted ${
            dense ? "text-[12.5px]" : "text-sm"
          }`}
        >
          {item.caption}
        </p>
      </figcaption>
    </figure>
  );
}
