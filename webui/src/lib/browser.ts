"use client";
import { useSyncExternalStore } from "react";

const noop = () => () => {};

/** A query-string value, read in the browser only (null while the page is being built or hydrated). */
export function useSearchParam(name: string): string | null {
  return useSyncExternalStore(
    noop,
    () => new URLSearchParams(window.location.search).get(name),
    () => null,
  );
}

/** The URL hash without the "#". */
export function useHash(): string {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener("hashchange", cb);
      return () => window.removeEventListener("hashchange", cb);
    },
    () => window.location.hash.replace("#", ""),
    () => "",
  );
}
