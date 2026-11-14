import { Link } from 'react-router-dom';
import { EmptyState, PageHeader } from '../components/ui';

export function Placeholder({ title }: { title: string }) {
  return <><PageHeader eyebrow="FIRE ATLAS / WORKSPACE" title={title} description="Исследования горения в малой гравитации. Условия, измерения и источники в одном пространстве." /><EmptyState title="Рабочее пространство готово"><span>Раздел подключается к общему API исследований.</span></EmptyState><p><Link to="/">Вернуться к обзору</Link></p></>;
}
