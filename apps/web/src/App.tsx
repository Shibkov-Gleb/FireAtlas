import { Route, Routes } from 'react-router-dom';
import { Shell } from './components/Shell';
import { Placeholder } from './pages/Placeholder';
import { Overview } from './pages/Overview';
import { Catalog } from './pages/Catalog';
import { InvestigationPage } from './pages/Investigation';
import { Measurements } from './pages/Measurements';
import { Compare } from './pages/Compare';
import { Missions } from './pages/Missions';
import { Ask } from './pages/Ask';

export function App() {
  return <Routes><Route element={<Shell />}>
    <Route index element={<Overview />} />
    <Route path="investigations" element={<Catalog />} />
    <Route path="investigations/:id" element={<InvestigationPage />} />
    <Route path="measurements" element={<Measurements />} />
    <Route path="compare" element={<Compare />} />
    <Route path="ask" element={<Ask />} />
    <Route path="missions" element={<Missions />} />
    <Route path="reports" element={<Placeholder title="Отчёты" />} />
    <Route path="*" element={<Placeholder title="Страница не найдена" />} />
  </Route></Routes>;
}
