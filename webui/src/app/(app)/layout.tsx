import type { ReactNode } from "react";
import Shell from "@/components/Shell";

/** Every signed-in page shares one Shell, so the live event stream and the top bar persist while you move around. */
export default function AppLayout({ children }: { children: ReactNode }) {
  return <Shell>{children}</Shell>;
}
