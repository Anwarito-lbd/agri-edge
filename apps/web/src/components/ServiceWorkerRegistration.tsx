"use client";

import { useEffect } from "react";

/** Registers public/sw.js in production builds (dev reloads fight a worker). */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => undefined);
  }, []);
  return null;
}

/** Tell the worker to forget cached farm data (called on logout). */
export function clearOfflineData() {
  navigator.serviceWorker?.controller?.postMessage({ type: "logout" });
}
