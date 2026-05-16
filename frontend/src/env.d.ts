/// <reference types="vite/client" />

declare module '*.module.css' {
  const classes: Readonly<Record<string, string>>;
  export default classes;
}

/**
 * Legacy API wrapper z app/web/index.html — stejné chování auth a chyb jako monolit.
 */
type LegacyApiCall = (
  endpoint: string,
  method?: string,
  data?: unknown,
  timeoutOrSignal?: number | AbortSignal
) => Promise<unknown>;

interface Window {
  apiCall?: LegacyApiCall;
  accessToken?: string | null;
  currentUser?: {
    email?: string | null;
  } | null;
}

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{
    outcome: 'accepted' | 'dismissed';
    platform: string;
  }>;
}
