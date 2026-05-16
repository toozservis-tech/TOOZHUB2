import { Component, type ErrorInfo, type ReactNode, StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { VehicleListApp } from './VehicleListApp';
import './styles/appShell.css';

class VehicleListErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[react-vehicles]', error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <p
          style={{
            margin: 0,
            padding: 8,
            color: '#b91c1c',
            fontSize: 14,
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          Modul seznamu vozidel se nepodařilo zobrazit. Podrobnosti v konzoli.
        </p>
      );
    }
    return this.props.children;
  }
}

const mountEl = document.getElementById('react-vehicles-root');
if (mountEl) {
  try {
    const root = createRoot(mountEl);
    root.render(
      <StrictMode>
        <VehicleListErrorBoundary>
          <VehicleListApp />
        </VehicleListErrorBoundary>
      </StrictMode>
    );
  } catch (e) {
    console.error('[react-vehicles] mount selhal:', e);
  }
}

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    void navigator.serviceWorker
      .register(`${import.meta.env.BASE_URL}sw.js`)
      .catch((error) => console.error('[react-vehicles] registrace service workeru selhala:', error));
  });
}
