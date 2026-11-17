import { Suspense } from "react";

import Explorer from "@/components/Explorer";

export default function Home() {
  return (
    <Suspense fallback={<p className="p-8 text-sm text-muted">Loading…</p>}>
      <Explorer />
    </Suspense>
  );
}
