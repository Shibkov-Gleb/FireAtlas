import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { EmptyState, PageHeader } from '../components/ui';
export function NotFound() {
  return (
    <>
      <PageHeader eyebrow="FIRE ATLAS / 404" title="Страница не найдена" />
      <EmptyState
        title="Такого раздела нет"
        action={
          <Link className="textLink" to="/">
            <ArrowLeft size={14} /> Открыть обзор
          </Link>
        }
      >
        Проверьте адрес или вернитесь к исследованиям.
      </EmptyState>
    </>
  );
}
