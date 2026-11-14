import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { WorkspaceProvider } from './state/WorkspaceProvider';
import './styles/global.css';

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

async function bootstrap() {
  // Keep the compile-time guard here so production omits the mock module entirely.
  if (import.meta.env.MODE === 'demo' && import.meta.env.VITE_USE_MOCKS === 'true') {
    const { worker } = await import('./mocks/browser');
    await worker.start({ onUnhandledFrame: 'bypass', quiet: true });
  }
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <WorkspaceProvider>
            <App />
          </WorkspaceProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
void bootstrap().catch((error) => {
  console.error('Application startup failed', error);
  const root = document.getElementById('root');
  if (root)
    root.textContent =
      'Не удалось запустить приложение. Обновите страницу или проверьте доступность сервера.';
});
