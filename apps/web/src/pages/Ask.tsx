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
      setValidation(`Enter a question with 3 to ${config.limits.question_chars_max} characters.`);
      return;
    }
    setValidation('');
    const job = await action.start({
      question: value,
      locale: 'en',
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
        eyebrow="AI / EVIDENCE-BASED EXPLANATION"
        title="Ask about the research"
        description="Your question uses the current mission and selected investigations. Observations, syntheses and limitations are shown separately."
        action={
          <Badge tone="purple">
            <Sparkles size={12} /> {IS_DEMO ? 'Prepared AI example' : 'Evidence-based answer'}
          </Badge>
        }
      />
      {!config.feature_flags.analysis ? (
        <Notice tone="warning">
          AI is currently unavailable.{' '}
          <Link to="/investigations">The catalog and sources remain available.</Link>
        </Notice>
      ) : (
        <>
          <Panel className={s.questionPanel}>
            <div className="spaceBetween">
              <h2>Your question</h2>
              <Badge tone="cyan">{workspace.scenario?.name ?? 'No scenario'}</Badge>
            </div>
            <form onSubmit={(event) => void submit(event)}>
              <label className="srOnly" htmlFor="analysis-question">
                Question for AI
              </label>
              <textarea
                id="analysis-question"
                value={question}
                maxLength={config.limits.question_chars_max}
                onChange={(event) => {
                  setQuestion(event.target.value);
                  setValidation('');
                }}
                placeholder="Why can weak ventilation sustain combustion in microgravity?"
                aria-invalid={!!validation}
                aria-describedby="analysis-hint"
                disabled={!!jobId}
              />
              <div className={s.questionMeta}>
                <span id="analysis-hint">
                  Conditions: {workspace.scenario?.name ?? 'No scenario'} · snapshot{' '}
                  {workspace.revision}
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
                <legend>Investigations for context · optional</legend>
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
                  <span>Only this button starts answer generation.</span>
                  <Button
                    type="submit"
                    busy={action.submitting}
                    disabled={workspacePending || !!action.pending}
                  >
                    <Sparkles size={14} /> Get answer <ArrowRight size={14} />
                  </Button>
                </div>
              )}
            </form>
          </Panel>
          {Boolean(action.error) && <ErrorState error={action.error} />}{' '}
          {action.pending && (
            <Notice tone="warning">
              <strong>The outcome of the previous request is unconfirmed.</strong> A retry uses the
              same key and original request body, including snapshot{' '}
              {action.pending.body.workspace_revision}.
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
                  Retry the same request
                </Button>
                <Button variant="ghost" onClick={newAction}>
                  Start a new action explicitly
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
                  Prepare another question
                </Button>
              </div>
            </>
          ) : (
            <div className={s.examples}>
              <span>Start with a question</span>
              <button
                onClick={() =>
                  setQuestion('How does ventilation affect the combustion of solid materials?')
                }
              >
                How does ventilation affect combustion? <ArrowRight size={12} />
              </button>
              <button
                onClick={() => setQuestion('What limits the transfer of findings to a lunar base?')}
              >
                What do we know about a lunar base? <ArrowRight size={12} />
              </button>
            </div>
          )}
          {IS_DEMO && (
            <p className={s.demoNote}>
              Demo mode shows a prepared example. No model request is made.
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
