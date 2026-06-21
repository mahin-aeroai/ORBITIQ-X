"use client";
/**
 * ORBITIQ-X — QueryProvider
 * ==========================
 * TanStack Query v5 client provider.
 * Wraps the entire app so all dashboard components can use useQuery.
 *
 * staleTime:   30 s — dashboard data refreshes every 30s
 * gcTime:      5 min — keep cached data for offline graceful degradation
 * retry:       2 — tolerate transient backend blips
 * refetchOnWindowFocus: false — mission control windows stay stable
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime:            30 * 1000,   // 30 seconds
            gcTime:               5 * 60 * 1000, // 5 minutes
            retry:                2,
            refetchOnWindowFocus: false,
            refetchIntervalInBackground: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {process.env.NODE_ENV === "development" && (
        <ReactQueryDevtools initialIsOpen={false} />
      )}
    </QueryClientProvider>
  );
}
