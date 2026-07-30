import { Suspense, type ReactNode } from "react";

export function DeferredPanel({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={(
        <div className="panel">
          <div className="empty-state">Loading workspace</div>
        </div>
      )}
    >
      {children}
    </Suspense>
  );
}
