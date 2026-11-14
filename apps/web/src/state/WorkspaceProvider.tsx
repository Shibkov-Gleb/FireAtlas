import { createContext, useContext, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api/client';
import type { Schema, Workspace } from '../api/types';
import { Button, Loading, Notice } from '../components/ui';
import { ErrorState } from '../components/ErrorState';

type Context = {
  config: Schema['Config']; workspace: Workspace;
  update: (patch: Schema['WorkspacePatch']) => Promise<boolean>;
  pending: boolean; conflict: Schema['WorkspacePatch'] | null;
  clearConflict: () => void; retryConflict: () => Promise<boolean>;
  toggleComparison: (id: string) => Promise<boolean>;
  toggleSaved: (id: string) => Promise<boolean>;
  saveAnswer: (id: string) => Promise<boolean>;
  notify: (message: string, tone?: 'info' | 'warning' | 'error') => void;
};
const WorkspaceContext = createContext<Context | null>(null);
export function useWorkspace() { const context = useContext(WorkspaceContext); if (!context) throw new Error('WorkspaceProvider is required'); return context; }

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [conflict, setConflict] = useState<Schema['WorkspacePatch'] | null>(null);
  const [notification, setNotification] = useState<{ message: string; tone: 'info' | 'warning' | 'error' } | null>(null);
  const [sessionLost, setSessionLost] = useState(false);
  const configQuery = useQuery({ queryKey: ['config'], queryFn: ({ signal }) => api.config(signal).then(r => r.data), staleTime: Infinity });
  const workspaceQuery = useQuery({ queryKey: ['workspace'], queryFn: async ({ signal }) => {
    try { const result = await api.workspace(signal); localStorage.setItem('fireatlas:has-workspace', '1'); return result.data; }
    catch (error) { if (error instanceof ApiError && error.code === 'SESSION_REQUIRED' && !localStorage.getItem('fireatlas:has-workspace')) { const result = await api.createWorkspace(); localStorage.setItem('fireatlas:has-workspace', '1'); return result.data; } throw error; }
  }, staleTime: Infinity });
  const mutation = useMutation({ mutationFn: ({ patch, revision }: { patch: Schema['WorkspacePatch']; revision: number }) => api.patchWorkspace(patch, revision).then(r => r.data), onSuccess: data => client.setQueryData(['workspace'], data) });
  const notify: Context['notify'] = (message, tone = 'info') => setNotification({ message, tone });
  async function update(patch: Schema['WorkspacePatch']) {
    const current = client.getQueryData<Workspace>(['workspace']); if (!current) return false;
    try { await mutation.mutateAsync({ patch, revision: current.revision }); setConflict(null); return true; }
    catch (error) {
      if (error instanceof ApiError && error.code === 'WORKSPACE_CONFLICT') { setConflict(patch); await client.invalidateQueries({ queryKey: ['workspace'] }); notify('Контекст обновлён из другой вкладки. Ваш выбор сохранён для повторного применения.', 'warning'); }
      else if (error instanceof ApiError && error.status === 401) setSessionLost(true);
      else notify(error instanceof Error ? error.message : 'Не удалось сохранить выбор.', 'error');
      return false;
    }
  }
  async function createNewWorkspace() {
    try { const result = await api.createWorkspace(); client.setQueryData(['workspace'], result.data); localStorage.setItem('fireatlas:has-workspace', '1'); setSessionLost(false); setConflict(null); notify('Гостевое пространство доступно.'); }
    catch (error) { notify(error instanceof Error ? error.message : 'Не удалось создать пространство.', 'error'); }
  }
  if (configQuery.isPending || workspaceQuery.isPending) return <Loading>Открываем рабочее пространство…</Loading>;
  if (workspaceQuery.error instanceof ApiError && workspaceQuery.error.status === 401 || sessionLost) return <div style={{ maxWidth: 650, margin: '12vh auto', padding: 24 }}><Notice tone="warning">Сессия гостевого пространства истекла. Для продолжения создайте новое пространство.</Notice><Button onClick={() => void createNewWorkspace()}>Создать гостевое пространство</Button></div>;
  if (configQuery.isError) return <div style={{ padding: 32 }}><ErrorState error={configQuery.error} onRetry={() => void configQuery.refetch()} /></div>;
  if (workspaceQuery.isError && !workspaceQuery.data) return <div style={{ padding: 32 }}><ErrorState error={workspaceQuery.error} onRetry={() => void workspaceQuery.refetch()} /></div>;
  const workspace = workspaceQuery.data!;
  const value: Context = { config: configQuery.data!, workspace, update, pending: mutation.isPending, conflict, clearConflict: () => setConflict(null), retryConflict: () => conflict ? update(conflict) : Promise.resolve(false), notify,
    toggleComparison: async id => { const current = client.getQueryData<Workspace>(['workspace'])!; const selected = current.selected_investigation_ids; if (!selected.includes(id) && selected.length >= configQuery.data!.limits.comparison_max) { notify('Можно сравнить не более трёх исследований. Уберите одно из выбранных.', 'warning'); return false; } return update({ selected_investigation_ids: selected.includes(id) ? selected.filter(item => item !== id) : [...selected, id] }); },
    toggleSaved: id => { const saved = client.getQueryData<Workspace>(['workspace'])!.saved_investigation_ids; if (!saved.includes(id) && saved.length >= 100) { notify('Можно сохранить не более 100 исследований.', 'warning'); return Promise.resolve(false); } return update({ saved_investigation_ids: saved.includes(id) ? saved.filter(item => item !== id) : [...saved, id] }); },
    saveAnswer: id => { const saved = client.getQueryData<Workspace>(['workspace'])!.saved_answer_ids; if (saved.includes(id)) return Promise.resolve(true); if (saved.length >= 30) { notify('Можно сохранить не более 30 ответов.', 'warning'); return Promise.resolve(false); } return update({ saved_answer_ids: [...saved, id] }); },
  };
  return <WorkspaceContext value={value}>{children}<div className="notificationRegion" aria-live="polite" aria-atomic="true">{notification && <div className={`notification ${notification.tone}`}><span>{notification.message}</span><button className="iconButton" aria-label="Закрыть уведомление" onClick={() => setNotification(null)}>×</button></div>}</div></WorkspaceContext>;
}
export function WorkspaceBanners() {
  const { conflict, clearConflict, retryConflict, pending } = useWorkspace();
  if (!conflict) return null;
  return <Notice tone="warning"><strong>Рабочий контекст изменился.</strong> Проверьте обновлённую миссию и выбор перед повтором.<div className="inline" style={{ marginTop: 10 }}><Button variant="secondary" busy={pending} onClick={() => void retryConflict()}>Применить мой выбор</Button><Button variant="ghost" onClick={clearConflict}>Оставить обновлённый контекст</Button></div></Notice>;
}
