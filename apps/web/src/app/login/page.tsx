"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { useI18n } from "@/components/I18nProvider";
import { safeNext } from "@/lib/safe-next";

function LoginForm() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const next = safeNext(params.get("next"));

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(e.currentTarget);
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
    }).catch(() => null);
    setBusy(false);
    if (res?.ok) {
      router.push(next);
      return;
    }
    setError(
      !res || res.status === 503
        ? t("login.unreachable")
        : res.status === 429
          ? t("login.locked")
          : t("login.failed"),
    );
  }

  return (
    <div className="mx-auto max-w-sm px-4 py-12">
      <h1 className="section-title text-2xl">{t("login.title")}</h1>
      <form onSubmit={(e) => void submit(e)} className="card mt-6 space-y-4 border border-border bg-white p-5">
        <label className="block text-sm font-medium">
          {t("login.username")}
          <input name="username" autoComplete="username" required className="mt-1 w-full rounded border border-border px-3 py-2" />
        </label>
        <label className="block text-sm font-medium">
          {t("login.password")}
          <input name="password" type="password" autoComplete="current-password" required className="mt-1 w-full rounded border border-border px-3 py-2" />
        </label>
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {t("login.submit")}
        </button>
        {error ? (
          <p role="alert" className="text-sm font-medium text-red-700">
            {error}
          </p>
        ) : null}
        <p className="text-xs text-muted">{t("login.note")}</p>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
