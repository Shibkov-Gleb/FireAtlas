import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import { emptyFilters } from './types';
import { useWorkspace } from '../state/WorkspaceProvider';

export function useInvestigationOptions() {
  const { workspace } = useWorkspace();
  return useQuery({ queryKey: ['investigation-options', workspace.data_revision], queryFn: ({ signal }) => api.search({ query: '', locale: 'ru', data_revision: workspace.data_revision, filters: { ...emptyFilters(), scopes: ['prevention','detection','suppression'] }, scenario: null, include_related: false, cursor: null, limit: 100 }, signal).then(result => result.data.items.map(item => item.investigation)), staleTime: 60000 });
}
