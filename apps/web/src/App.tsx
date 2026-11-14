import { lazy } from 'react';
import { Route, Routes } from 'react-router-dom';
import { Shell } from './components/Shell';
import { Overview } from './pages/Overview';
import { NotFound } from './pages/NotFound';
const Catalog = lazy(() => import('./pages/Catalog').then((m) => ({ default: m.Catalog })));
const InvestigationPage = lazy(() =>
  import('./pages/Investigation').then((m) => ({ default: m.InvestigationPage })),
);
const Measurements = lazy(() =>
  import('./pages/Measurements').then((m) => ({ default: m.Measurements })),
);
const Compare = lazy(() => import('./pages/Compare').then((m) => ({ default: m.Compare })));
const Missions = lazy(() => import('./pages/Missions').then((m) => ({ default: m.Missions })));
const Ask = lazy(() => import('./pages/Ask').then((m) => ({ default: m.Ask })));
const Reports = lazy(() => import('./pages/Reports').then((m) => ({ default: m.Reports })));
export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Overview />} />
        <Route path="investigations" element={<Catalog />} />
        <Route path="investigations/:id" element={<InvestigationPage />} />
        <Route path="measurements" element={<Measurements />} />
        <Route path="compare" element={<Compare />} />
        <Route path="ask" element={<Ask />} />
        <Route path="missions" element={<Missions />} />
        <Route path="reports" element={<Reports />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
