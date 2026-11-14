import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Clock3, LoaderCircle, X } from 'lucide-react';
import { api, ApiError } from '../api/client';
import { useJob } from '../api/jobs';
import { isTerminal, type Job } from '../api/types';
import { useWorkspace } from '../state/WorkspaceProvider';
import { formatDate } from '../lib/format';
import { Badge, Button, Loading, Notice, Panel } from './ui';
import { ErrorState } from './ErrorState';
import s from './JobStatus.module.css';

const stageLabels: Record<string, string> = {
  retrieving: 'Ищем основания',
  reasoning: 'Готовим объяснение',
  validating: 'Проверяем ссылки и числа',
  exporting: 'Готовим PDF',
};
export function JobStatus({
  id,
  query,
  onEvidence,
  onNewAction,
}: {
  id: string;
  query: ReturnType<typeof useJob>;
  onEvidence?: (id: string) => void;
  onNewAction?: () => void;
}) {
  const client = useQueryClient();
  const { workspace } = useWorkspace();
  const [clock, setClock] = useState(Date.now());
  const job = query.data?.data;
  useEffect(() => {
    if (!job || isTerminal(job.state)) return;
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [job?.id, job?.state]);
  const cancel = useMutation({
    mutationFn: () => api.cancelJob(id),
    onSuccess: () => client.invalidateQueries({ queryKey: ['job', id] }),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409)
        void client.invalidateQueries({ queryKey: ['job', id] });
    },
  });
  if (!job && query.isPending) return <Loading>Восстанавливаем задачу…</Loading>;
  if (!job && query.isError)
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (!job) return null;
  const active = !isTerminal(job.state),
    deadlineReached = clock >= Date.parse(job.deadline_at);
  const stateLabels: Record<Job['state'], string> = {
    queued: 'В очереди',
    running: 'Выполняется',
    succeeded: 'Готово',
    failed: 'Не удалось завершить',
    cancelled: 'Отменено',
    expired: 'Истёк срок',
  };
  return (
    <Panel className={s.panel}>
      <div className="spaceBetween">
        <div className={s.title}>
          {job.state === 'succeeded' ? (
            <CheckCircle2 size={20} />
          ) : active ? (
            <LoaderCircle size={20} className={s.spin} />
          ) : (
            <Clock3 size={20} />
          )}
          <h2>
            {active
              ? (stageLabels[job.stage ?? ''] ?? 'Ожидаем начала задачи')
              : stateLabels[job.state]}
          </h2>
        </div>
        <Badge tone={job.state === 'succeeded' ? 'teal' : active ? 'cyan' : 'orange'}>
          {stateLabels[job.state]}
        </Badge>
      </div>
      <p className={s.context}>
        Контекст задачи: {job.input_context.scenario_id} · ревизия пространства{' '}
        {job.input_context.workspace_revision}
        <br />
        Корпус: {job.input_context.data_revision}
      </p>
      {job.input_context.workspace_revision !== workspace.revision && (
        <Notice tone="warning">
          Задача относится к предыдущему снимку пространства. Её результат сохранит исходные
          условия.
        </Notice>
      )}
      {active && (
        <>
          <div className={s.stages}>
            {(job.type === 'analysis'
              ? ['retrieving', 'reasoning', 'validating']
              : ['exporting']
            ).map((stage) => (
              <span key={stage} className={job.stage === stage ? s.current : ''}>
                {stageLabels[stage]}
              </span>
            ))}
          </div>
          <div className="spaceBetween">
            <span className="tiny muted">Дедлайн: {formatDate(job.deadline_at)}</span>
            <Button variant="ghost" busy={cancel.isPending} onClick={() => cancel.mutate()}>
              <X size={14} /> Отменить задачу
            </Button>
          </div>
        </>
      )}
      {active && deadlineReached && (
        <Notice tone="warning">
          Дедлайн ожидания достигнут. Проверьте состояние сервера; новый анализ автоматически не
          запускается.
          <div style={{ marginTop: 12 }}>
            <Button variant="secondary" onClick={() => void query.refetch()}>
              Проверить состояние
            </Button>
          </div>
        </Notice>
      )}
      {query.isError && job && (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      )}
      {cancel.isError && !(cancel.error instanceof ApiError && cancel.error.status === 409) && (
        <ErrorState error={cancel.error} />
      )}{' '}
      {job.error && (
        <ErrorState
          error={
            new ApiError(
              job.error.code,
              job.error.message,
              0,
              query.data?.meta.request_id,
              job.error.retryable,
              job.error.details,
            )
          }
        />
      )}{' '}
      {job.fallback_evidence_ids.length > 0 && (
        <div className={s.fallback}>
          <h3>Найденные материалы остаются доступны</h3>
          <p>
            Непроверенный ответ не опубликован. Откройте основания для самостоятельного изучения.
          </p>
          <div className="inline">
            {job.fallback_evidence_ids.map((id, index) => (
              <Button key={id} variant="secondary" onClick={() => onEvidence?.(id)}>
                Источник {index + 1}
              </Button>
            ))}
          </div>
        </div>
      )}
      {!active && job.state !== 'succeeded' && onNewAction && (
        <Button variant="secondary" onClick={onNewAction}>
          Вернуться к новому действию
        </Button>
      )}
      <details className={s.details}>
        <summary>Детали задачи</summary>
        <code className="wordBreak">{job.id}</code>
        <br />
        <span>{query.data?.meta.request_id}</span>
      </details>
    </Panel>
  );
}
