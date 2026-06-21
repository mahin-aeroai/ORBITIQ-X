"use client";
/**
 * ORBITIQ-X — ThemeProvider
 * ==========================
 * next-themes wrapper. Platform is dark-only by design.
 * ThemeProvider is kept for future light-mode operator preference support
 * and to suppress hydration mismatch on SSR.
 */

import { ThemeProvider as NextThemesProvider } from "next-themes";

type ThemeProviderProps = React.ComponentProps<typeof NextThemesProvider>;

export function ThemeProvider({ children, ...props }: ThemeProviderProps) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}
