import { IS_DEMO } from '../lib/env';
import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, Sparkles } from 'lucide-react';
import { ApiError } from '../api/client';
import { useJob, useJobSubmission } from '../api/jobs';
import { useInvestigationOptions } from '../api/hooks';
import type { Schema } from '../api/types';
import { useWorkspace } from '../state/WorkspaceProvider';
import { Badge, Button, Notice, PageHeader, Panel } from '../components/ui';
import { ErrorState } from '../components/ErrorState';
import { JobStatus } from '../components/JobStatus';
import { EvidenceDrawer } from '../components/EvidenceDrawer';
import { AnswerView } from '../components/AnswerView';
import s from './Ask.module.css';

export function Ask() {
  const { workspace, config, pending: workspacePending, toggleComparison } = useWorkspace();
  const options = useInvestigationOptions();
  const [params, setParams] = useSearchParams();
  const action = useJobSubmission<Schema['AnalysisRequest']>('analysis', workspace.id);
  const [question, setQuestion] = useState(params.get('q') ?? action.pending?.body.question ?? '');
  const [validation, setValidation] = useState('');
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const jobId = params.get('job');
  const jobQuery = useJob(jobId);
  function prepareQuestion(value: string) {
    action.discard();
    setQuestion(value);
    const next = new URLSearchParams(params);
    next.delete('job');
    next.set('q', value);
    setParams(next);
  }
  function accepted(id: string, submittedQuestion = question) {
    const next = new URLSearchParams(params);
    next.set('job', id);
    next.set('q', submittedQuestion);
    setParams(next);
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = question.trim();
    if (value.length < 3 || value.length > config.limits.question_chars_max) {
      setValidation(`Введите вопрос от 3 до ${config.limits.question_chars_max} символов.`);
      return;
    }
    setValidation('');
    const job = await action.start({
      question: value,
      locale: 'ru',
      workspace_revision: workspace.revision,
      data_revision: workspace.data_revision,
      selected_investigation_ids: workspace.selected_investigation_ids,
      mode: 'evidence_answer',
    });
    if (job) accepted(job.id, value);
  }
  function newAction() {
    action.discard();
    const next = new URLSearchParams(params);
    next.delete('job');
    setParams(next);
  }
  return (
    <>
      <PageHeader
        eyebrow="AI / ОБЪЯСНЕНИЕ С ОСНОВАНИЯМИ"
        title="Спросить по исследованиям"
        description="Вопрос связывается с текущей миссией и выбранными исследованиями. Наблюдения, обобщения и ограничения показываются отдельно."
        action={
          <Badge tone="purple">
            <Sparkles size={12} />{' '}
            {IS_DEMO ? 'Подготовленный AI-пример' : 'Ответ по доказательствам'}
          </Badge>
        }
      />
      {!config.feature_flags.analysis ? (
        <Notice tone="warning">
          AI сейчас недоступен.{' '}
          <Link to="/investigations">Каталог и источники продолжают работать.</Link>
        </Notice>
      ) : (
        <>
          <Panel className={s.questionPanel}>
            <div className="spaceBetween">
              <h2>Ваш вопрос</h2>
              <Badge tone="cyan">{workspace.scenario.name}</Badge>
            </div>
            <form onSubmit={(event) => void submit(event)}>
              <label className="srOnly" htmlFor="analysis-question">
                Вопрос для AI
              </label>
              <textarea
                id="analysis-question"
                value={question}
                maxLength={config.limits.question_chars_max}
                onChange={(event) => {
                  setQuestion(event.target.value);
                  setValidation('');
                }}
                placeholder="Почему слабая вентиляция может поддерживать горение в невесомости?"
                aria-invalid={!!validation}
                aria-describedby="analysis-hint"
                disabled={!!jobId}
              />
              <div className={s.questionMeta}>
                <span id="analysis-hint">
                  Условия: {workspace.scenario.name} · снимок {workspace.revision}
                </span>
                <span>
                  {question.length}/{config.limits.question_chars_max}
                </span>
              </div>
              {validation && (
                <p className="errorText" role="alert">
                  {validation}
                </p>
              )}
              <fieldset className={s.selection} disabled={workspacePending || !!jobId}>
                <legend>Исследования для контекста · необязательно</legend>
                <div className="inline">
                  {options.data?.map((inv) => (
                    <label className="checkLabel" key={inv.id}>
                      <input
                        type="checkbox"
                        checked={workspace.selected_investigation_ids.includes(inv.id)}
                        onChange={() => void toggleComparison(inv.id)}
                      />
                      {inv.acronym}
                    </label>
                  ))}
                </div>
              </fieldset>
              {!jobId && (
                <div className={s.submitRow}>
                  <span>Генерация запускается только этой кнопкой.</span>
                  <Button
                    type="submit"
                    busy={action.submitting}
                    disabled={workspacePending || !!action.pending}
                  >
                    <Sparkles size={14} /> Получить ответ <ArrowRight size={14} />
                  </Button>
                </div>
              )}
            </form>
          </Panel>
          {Boolean(action.error) && <ErrorState error={action.error} />}{' '}
          {action.pending && (
            <Notice tone="warning">
              <strong>Исход предыдущего запроса не подтверждён.</strong> Повтор использует тот же
              ключ и исходное тело, включая снимок {action.pending.body.workspace_revision}.
              <div className="inline" style={{ marginTop: 13 }}>
                <Button
                  variant="secondary"
                  busy={action.submitting}
                  disabled={action.error instanceof ApiError && !action.error.retryable}
                  onClick={() => {
                    const original = action.pending!.body.question;
                    void action.retry().then((job) => {
                      if (job) {
                        setQuestion(original);
                        accepted(job.id, original);
                      }
                    });
                  }}
                >
                  Повторить тот же запрос
                </Button>
                <Button variant="ghost" onClick={newAction}>
                  Явно начать новое действие
                </Button>
              </div>
            </Notice>
          )}
          {jobId ? (
            <>
              <JobStatus
                id={jobId}
                query={jobQuery}
                onEvidence={setEvidenceId}
                onNewAction={newAction}
              />
              {jobQuery.data?.data.state === 'succeeded' && jobQuery.data.data.result_id && (
                <AnswerView
                  id={jobQuery.data.data.result_id}
                  revision={jobQuery.data.data.input_context.data_revision}
                  onAsk={prepareQuestion}
                />
              )}
              <div style={{ marginTop: 20 }}>
                <Button variant="ghost" onClick={newAction}>
                  Подготовить другой вопрос
                </Button>
              </div>
            </>
          ) : (
            <div className={s.examples}>
              <span>Можно начать с вопроса</span>
              <button
                onClick={() => setQuestion('Как вентиляция влияет на горение твёрдых материалов?')}
              >
                Как влияет вентиляция? <ArrowRight size={12} />
              </button>
              <button
                onClick={() =>
                  setQuestion('Какие ограничения есть при переносе результатов на лунную базу?')
                }
              >
                Что известно для лунной базы? <ArrowRight size={12} />
              </button>
            </div>
          )}
          {IS_DEMO && (
            <p className={s.demoNote}>
              Демонстрационный режим: показывается заранее подготовленный пример. Запрос к модели не
              выполняется.
            </p>
          )}
        </>
      )}
      <EvidenceDrawer
        id={evidenceId}
        revision={workspace.data_revision}
        onClose={() => setEvidenceId(null)}
      />
    </>
  );
}
