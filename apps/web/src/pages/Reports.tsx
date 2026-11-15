import { IS_DEMO } from '../lib/env';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQueries, useQuery } from '@tanstack/react-query';
import { ArrowRight, Download, FileText, LoaderCircle, Plus } from 'lucide-react';
import { api, ApiError } from '../api/client';
import { useJob, useJobSubmission } from '../api/jobs';
import { useInvestigationOptions } from '../api/hooks';
import type { Schema } from '../api/types';
import { useWorkspace } from '../state/WorkspaceProvider';
import { formatDate } from '../lib/format';
import { Badge, Button, EmptyState, Loading, Notice, PageHeader, Panel } from '../components/ui';
import { ErrorState } from '../components/ErrorState';
import { JobStatus } from '../components/JobStatus';
import s from './Reports.module.css';

export function Reports() {
  const { workspace, config, toggleSaved, pending: workspacePending } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const options = useInvestigationOptions();
  const action = useJobSubmission<Schema['ReportRequest']>('report', workspace.id);
  const [title, setTitle] = useState(
    params.get('title') ??
      action.pending?.body.title ??
      'Исследования горения: источники и ограничения',
  );
  const [selectedInv, setSelectedInv] = useState(workspace.saved_investigation_ids);
  const [selectedAnswers, setSelectedAnswers] = useState(workspace.saved_answer_ids);
  const [includeComparison, setIncludeComparison] = useState(false);
  const [validation, setValidation] = useState('');
  const [downloadError, setDownloadError] = useState<unknown>(null);
  const [downloading, setDownloading] = useState(false);
  const previousInv = useRef(workspace.saved_investigation_ids),
    previousAnswers = useRef(workspace.saved_answer_ids);
  useEffect(() => {
    const ids = workspace.saved_investigation_ids;
    const added = ids.filter((id) => !previousInv.current.includes(id));
    setSelectedInv((current) => [
      ...new Set([...current.filter((id) => ids.includes(id)), ...added]),
    ]);
    previousInv.current = ids;
  }, [JSON.stringify(workspace.saved_investigation_ids)]);
  useEffect(() => {
    const ids = workspace.saved_answer_ids;
    const added = ids.filter((id) => !previousAnswers.current.includes(id));
    setSelectedAnswers((current) => [
      ...new Set([...current.filter((id) => ids.includes(id)), ...added]),
    ]);
    previousAnswers.current = ids;
  }, [JSON.stringify(workspace.saved_answer_ids)]);
  useEffect(() => {
    if (selectedInv.length < 2 || selectedInv.length > 3) setIncludeComparison(false);
  }, [selectedInv.length]);
  const answerQueries = useQueries({
    queries: workspace.saved_answer_ids.map((id) => ({
      queryKey: ['answer', id, workspace.data_revision],
      queryFn: ({ signal }: { signal: AbortSignal }) => api.answer(id, signal).then((r) => r.data),
      staleTime: Infinity,
    })),
  });
  const answers = answerQueries.flatMap((query) => (query.data ? [query.data] : []));
  const jobId = params.get('job');
  const jobQuery = useJob(jobId);
  const reportId = jobQuery.data?.data.state === 'succeeded' ? jobQuery.data.data.result_id : null;
  const reportQuery = useQuery({
    queryKey: ['report', reportId],
    queryFn: ({ signal }) => api.report(reportId!, signal).then((r) => r.data),
    enabled: !!reportId,
  });
  const contexts = new Set(
    answers
      .filter((answer) => selectedAnswers.includes(answer.id))
      .map((answer) => JSON.stringify(answer.scenario_snapshot)),
  );
  function accepted(id: string, reportTitle = title) {
    const next = new URLSearchParams(params);
    next.set('job', id);
    next.set('title', reportTitle);
    setParams(next);
  }
  function newReport() {
    action.discard();
    setDownloadError(null);
    const next = new URLSearchParams(params);
    next.delete('job');
    setParams(next);
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (title.trim().length < 3 || title.length > 120) {
      setValidation('Название должно содержать от 3 до 120 символов.');
      return;
    }
    if (!selectedInv.length && !selectedAnswers.length) {
      setValidation('Выберите хотя бы одно исследование или сохранённый ответ.');
      return;
    }
    setValidation('');
    const job = await action.start({
      workspace_revision: workspace.revision,
      title: title.trim(),
      answer_ids: selectedAnswers,
      investigation_ids: selectedInv,
      include_comparison: includeComparison,
      locale: 'ru',
    });
    if (job) accepted(job.id, title.trim());
  }
  async function download() {
    const path = reportQuery.data?.download_path;
    if (!path) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const result = await api.downloadReport(path);
      const url = URL.createObjectURL(result.data);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `fire-atlas-${reportQuery.data!.id}.pdf`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setDownloadError(error);
    } finally {
      setDownloading(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="ОТЧЁТЫ / СОХРАНЁННАЯ АРГУМЕНТАЦИЯ"
        title="Исследовательский отчёт"
        description="Сохраните выбранные исследования, ответы, условия и ограничения. Каждый ответ остаётся связан со своим исходным контекстом."
        action={
          <Badge tone="cyan">
            <FileText size={12} /> PDF
          </Badge>
        }
      />
      {!config.feature_flags.reports ? (
        <Notice tone="warning">
          Экспорт временно недоступен. Сохранённые материалы остаются в рабочем пространстве.
        </Notice>
      ) : jobId ? (
        <>
          <JobStatus id={jobId} query={jobQuery} onNewAction={newReport} />
          {reportId &&
            (reportQuery.isPending ? (
              <Loading>Открываем сведения об отчёте…</Loading>
            ) : reportQuery.isError ? (
              <ErrorState error={reportQuery.error} onRetry={() => void reportQuery.refetch()} />
            ) : (
              reportQuery.data && (
                <Panel className={s.ready}>
                  <span className={s.pdfIcon}>
                    <FileText size={27} />
                  </span>
                  <div>
                    <Badge tone={reportQuery.data.state === 'ready' ? 'teal' : 'orange'}>
                      {reportQuery.data.state === 'ready'
                        ? 'Готов к скачиванию'
                        : reportQuery.data.state}
                    </Badge>
                    <h2>{reportQuery.data.title}</h2>
                    <p>
                      Снимок пространства: {reportQuery.data.source_workspace_revision} ·{' '}
                      {reportQuery.data.data_revision}
                    </p>
                    <p>Доступен до {formatDate(reportQuery.data.expires_at)}</p>
                  </div>
                  <Button
                    busy={downloading}
                    disabled={reportQuery.data.state !== 'ready' || !reportQuery.data.download_path}
                    onClick={() => void download()}
                  >
                    <Download size={15} /> Скачать PDF
                  </Button>
                </Panel>
              )
            ))}
          {Boolean(downloadError) && (
            <ErrorState error={downloadError} onRetry={() => void download()} />
          )}
          <div style={{ marginTop: 24 }}>
            <Button variant="secondary" onClick={newReport}>
              Подготовить другой отчёт
            </Button>
          </div>
        </>
      ) : (
        <form onSubmit={(event) => void submit(event)}>
          <div className={s.layout}>
            <div className="stack">
              <Panel className={s.composition}>
                <h2>Состав отчёта</h2>
                <label className="field">
                  Название отчёта
                  <input
                    value={title}
                    onChange={(e) => {
                      setTitle(e.target.value);
                      setValidation('');
                    }}
                    minLength={3}
                    maxLength={120}
                  />
                </label>
                <h3>Сохранённые исследования</h3>
                {workspace.saved_investigation_ids.length ? (
                  workspace.saved_investigation_ids.map((id) => (
                    <label className={s.savedItem} key={id}>
                      <input
                        type="checkbox"
                        checked={selectedInv.includes(id)}
                        onChange={() =>
                          setSelectedInv((current) =>
                            current.includes(id)
                              ? current.filter((value) => value !== id)
                              : [...current, id],
                          )
                        }
                      />
                      <span>
                        <strong>{options.data?.find((inv) => inv.id === id)?.acronym ?? id}</strong>
                        <small>{options.data?.find((inv) => inv.id === id)?.title}</small>
                      </span>
                    </label>
                  ))
                ) : (
                  <p className="tiny muted">Пока нет сохранённых исследований.</p>
                )}
                <details className={s.add}>
                  <summary>
                    <Plus size={12} /> Добавить исследования
                  </summary>
                  {options.isPending ? (
                    <Loading />
                  ) : options.isError ? (
                    <ErrorState error={options.error} onRetry={() => void options.refetch()} />
                  ) : (
                    options.data.map((inv) => (
                      <label className="checkLabel" key={inv.id}>
                        <input
                          type="checkbox"
                          checked={workspace.saved_investigation_ids.includes(inv.id)}
                          disabled={workspacePending}
                          onChange={() => void toggleSaved(inv.id)}
                        />
                        {inv.acronym}
                      </label>
                    ))
                  )}
                </details>
                <h3>Сохранённые ответы</h3>
                {answerQueries.some((query) => query.isPending) && <Loading />}
                {answerQueries.map((query, index) =>
                  query.isError ? (
                    <ErrorState
                      key={index}
                      error={query.error}
                      onRetry={() => void query.refetch()}
                    />
                  ) : null,
                )}
                {answers.length ? (
                  answers.map((answer) => (
                    <label className={s.savedItem} key={answer.id}>
                      <input
                        type="checkbox"
                        checked={selectedAnswers.includes(answer.id)}
                        onChange={() =>
                          setSelectedAnswers((current) =>
                            current.includes(answer.id)
                              ? current.filter((value) => value !== answer.id)
                              : [...current, answer.id],
                          )
                        }
                      />
                      <span>
                        <strong>{answer.question}</strong>
                        <small>
                          {answer.scenario_snapshot?.name ?? 'Без сценария'} ·{' '}
                          {formatDate(answer.created_at)}
                          <br />
                          {answer.data_revision} · снимок {answer.workspace_revision}
                        </small>
                      </span>
                    </label>
                  ))
                ) : (
                  <p className="tiny muted">
                    Сохраните ответ на экране «Спросить AI», чтобы включить его в отчёт.
                  </p>
                )}
                <div className="divider" />
                <label className="checkLabel">
                  <input
                    type="checkbox"
                    checked={includeComparison}
                    disabled={selectedInv.length < 2 || selectedInv.length > 3}
                    onChange={(e) => setIncludeComparison(e.target.checked)}
                  />
                  Включить сравнение выбранных исследований
                </label>
                <p className="tiny muted" style={{ marginTop: 9 }}>
                  Для сравнения выберите два или три исследования.
                </p>
              </Panel>
              <Notice>
                Гостевое пространство хранится {config.retention.workspace_days} суток. Готовый
                отчёт доступен {config.retention.report_hours} часа. Повтор скачивания не запускает
                AI.
              </Notice>
            </div>
            <Panel className={s.preview}>
              <span className={s.previewLabel}>ПРЕДПРОСМОТР СОСТАВА</span>
              <div className={s.document}>
                <div className={s.documentBrand}>
                  FIRE ATLAS <span>RESEARCH BRIEF</span>
                </div>
                <h2>{title || 'Название отчёта'}</h2>
                <p className={s.context}>
                  Текущая миссия: {workspace.scenario?.name ?? 'Без сценария'}
                  <br />
                  Корпус: {workspace.data_revision}
                </p>
                <div className={s.documentDivider} />
                <h3>Исследования</h3>
                {selectedInv.length ? (
                  <ul>
                    {selectedInv.map((id) => (
                      <li key={id}>{options.data?.find((inv) => inv.id === id)?.acronym ?? id}</li>
                    ))}
                  </ul>
                ) : (
                  <p>Исследования не выбраны.</p>
                )}
                <h3>Ответы и их контексты</h3>
                {answers
                  .filter((answer) => selectedAnswers.includes(answer.id))
                  .map((answer) => (
                    <div className={s.answerPreview} key={answer.id}>
                      <strong>{answer.scenario_snapshot?.name ?? 'Без сценария'}</strong>
                      <p>{answer.question}</p>
                    </div>
                  ))}
                {!selectedAnswers.length && <p>Ответы не выбраны.</p>}
                <h3>Источники и ограничения</h3>
                <p>
                  Добавляются с сохранёнными материалами. Разные контексты остаются отдельными
                  разделами.
                </p>
                {includeComparison && <Badge tone="cyan">Сравнение включено</Badge>}
              </div>
            </Panel>
          </div>
          {contexts.size > 1 && (
            <Notice tone="warning">
              Выбраны ответы из нескольких контекстов. Они будут включены отдельными разделами, без
              общего вывода.
            </Notice>
          )}
          {validation && (
            <p className="errorText" role="alert">
              {validation}
            </p>
          )}
          {Boolean(action.error) && <ErrorState error={action.error} />}{' '}
          {action.pending && (
            <Notice tone="warning">
              Запрос экспорта не подтверждён. Повтор сохраняет исходный состав и тот же ключ.
              <div className="inline" style={{ marginTop: 12 }}>
                <Button
                  variant="secondary"
                  busy={action.submitting}
                  disabled={action.error instanceof ApiError && !action.error.retryable}
                  onClick={() => {
                    const original = action.pending!.body.title;
                    void action.retry().then((job) => {
                      if (job) accepted(job.id, original);
                    });
                  }}
                >
                  Повторить тот же экспорт
                </Button>
                <Button variant="ghost" onClick={newReport}>
                  Явно начать новый экспорт
                </Button>
              </div>
            </Notice>
          )}
          <div className={s.export}>
            <span>Экспорт использует сохранённые ответы и фиксирует снимок пространства.</span>
            <Button
              type="submit"
              busy={action.submitting}
              disabled={
                workspacePending ||
                !!action.pending ||
                answerQueries.some((q) => q.isPending || q.isError)
              }
            >
              <FileText size={15} /> Подготовить PDF <ArrowRight size={14} />
            </Button>
          </div>
        </form>
      )}
      {IS_DEMO && (
        <Notice tone="warning">
          <strong>Демонстрационный экспорт.</strong> Скачивается маркированный PDF-пример. Он не
          отражает текущий состав; сборка отчёта по снимку выполняется будущим сервером.
        </Notice>
      )}
    </>
  );
}
