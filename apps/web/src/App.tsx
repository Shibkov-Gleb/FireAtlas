import { Route, Routes } from 'react-router-dom';
import { Shell } from './components/Shell';
import { Placeholder } from './pages/Placeholder';
import { Overview } from './pages/Overview';
import { Catalog } from './pages/Catalog';

export function App() {
  return <Routes><Route element={<Shell />}>
    <Route index element={<Overview />} />
    <Route path="investigations" element={<Catalog />} />
    <Route path="investigations/:id" element={<Placeholder title="Карточка исследования" />} />
    <Route path="measurements" element={<Placeholder title="Измерения" />} />
    <Route path="compare" element={<Placeholder title="Сравнение" />} />
    <Route path="ask" element={<Placeholder title="Спросить AI" />} />
    <Route path="missions" element={<Placeholder title="Сценарии миссий" />} />
    <Route path="reports" element={<Placeholder title="Отчёты" />} />
    <Route path="*" element={<Placeholder title="Страница не найдена" />} />
  </Route></Routes>;
}
