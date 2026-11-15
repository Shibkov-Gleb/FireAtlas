import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { EmptyState, PageHeader } from '../components/ui';
export function NotFound() {
  return (
    <>
      <PageHeader eyebrow="FIRE ATLAS / 404" title="Page not found" />
      <EmptyState
        title="This section does not exist"
        action={
          <Link className="textLink" to="/">
            <ArrowLeft size={14} /> Open overview
          </Link>
        }
      >
        Check the URL or return to investigations.
      </EmptyState>
    </>
  );
}
