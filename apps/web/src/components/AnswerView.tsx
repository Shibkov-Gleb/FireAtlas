import { IS_DEMO } from '../lib/env';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bookmark, Check, ArrowUpRight, FileText, Sparkles } from 'lucide-react';
import { api } from '../api/client';
import type { AnalysisResult } from '../api/types';
import { useWorkspace } from '../state/WorkspaceProvider';
import { formatDate } from '../lib/format';
import { Badge, Button, Loading, Notice, Panel } from './ui';
import { ErrorState } from './ErrorState';
import { EvidenceDrawer } from './EvidenceDrawer';
import { QuantityValue } from './RunPanel';
import { ApplicabilityView } from './ApplicabilityView';
import s from './AnswerView.module.css';

const blockLabels = {
  summary: 'Summary',
  observation: 'Observation',
  synthesis: 'Synthesis',
  limitation: 'Limitation',
} as const;
export function AnswerBlocks({
  answer,
  onEvidence,
}: {
  answer: Pick<AnalysisResult, 'answer_blocks' | 'citations'>;
  onEvidence: (id: string) => void;
}) {
  return (
    <div className="stack">
      {answer.answer_blocks.map((block) => (
        <section key={block.id} className={`${s.block} ${s[block.kind]}`}>
          <div className={s.blockLabel}>{blockLabels[block.kind]}</div>
          <p>{block.text}</p>
          {block.evidence_ids.length > 0 && (
            <div className={s.references}>
              {block.evidence_ids.map((id) => {
                const citation = answer.citations.find((c) => c.evidence_id === id);
                return (
                  <button key={id} className="textLink" onClick={() => onEvidence(id)}>
                    <span>[{answer.citations.findIndex((c) => c.evidence_id === id) + 1}]</span>{' '}
                    {citation?.label ?? 'Evidence'} <ArrowUpRight size={11} />
                  </button>
                );
              })}
            </div>
          )}
          {block.quantities.length > 0 && (
            <details className={s.quantities}>
              <summary>Numbers and original values</summary>
              {block.quantities.map((entry, index) => (
                <div key={index}>
                  <span>
                    {{
                      burn_duration: 'Burn duration',
                      initial_diameter: 'Initial diameter',
                      pressure: 'Pressure',
                    }[entry.name as 'burn_duration'] ?? entry.name}
                  </span>
                  <QuantityValue quantity={entry.quantity} />
                  {entry.evidence_ids.map((id) => (
                    <button className="textLink" key={id} onClick={() => onEvidence(id)}>
                      Source row
                    </button>
                  ))}
                </div>
              ))}
            </details>
          )}
        </section>
      ))}
    </div>
  );
}
export function AnswerView({
  id,
  revision,
  onAsk,
}: {
  id: string;
  revision: string;
  onAsk: (question: string) => void;
}) {
  const { workspace, saveAnswer, pending, notify } = useWorkspace();
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ['answer', id, revision],
    queryFn: ({ signal }) => api.answer(id, signal).then((r) => r.data),
    staleTime: Infinity,
  });
  if (query.isPending) return <Loading>Opening result…</Loading>;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const answer = query.data;
  if (!Object.values(answer.validation_summary).every(Boolean))
    return (
      <Notice tone="error">
        The answer failed the required validation and has not been published.
      </Notice>
    );
  const oldContext = answer.workspace_revision !== workspace.revision;
  const saved = workspace.saved_answer_ids.includes(answer.id);
  return (
    <section className={s.answer}>
      <div className="spaceBetween">
        <div className="inline">
          <Badge tone={answer.status === 'answered' ? 'teal' : 'orange'}>
            {answer.status === 'answered'
              ? 'Answer ready'
              : answer.status === 'insufficient_evidence'
                ? 'Insufficient evidence'
                : 'Conflicting evidence'}
          </Badge>
          {IS_DEMO && (
            <Badge tone="purple">
              <Sparkles size={12} /> Prepared example
            </Badge>
          )}
        </div>
        <Button
          variant="secondary"
          disabled={pending || saved}
          onClick={() =>
            void saveAnswer(answer.id).then((ok) => {
              if (ok) notify('Answer saved with its original context.');
            })
          }
        >
          {saved ? <Check size={14} /> : <Bookmark size={14} />}{' '}
          {saved ? 'Answer saved' : 'Save answer'}
        </Button>
      </div>
      <Panel className={s.context}>
        <h2>Answer context: {answer.scenario_snapshot?.name ?? 'No scenario'}</h2>
        <p>{answer.question}</p>
        <div className={s.metadata}>
          <span>{formatDate(answer.created_at)}</span>
          <span>Workspace: {answer.workspace_revision}</span>
          <span>Corpus: {answer.data_revision}</span>
        </div>
        <details>
          <summary>Captured conditions</summary>
          <dl>
            <div>
              <dt>Gravity</dt>
              <dd>{answer.scenario_snapshot?.gravity_regime}</dd>
            </div>
            {(
              [
                ['Oxygen', answer.scenario_snapshot?.oxygen_fraction],
                ['Pressure', answer.scenario_snapshot?.pressure],
                ['Airflow speed', answer.scenario_snapshot?.airflow_speed],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value ? <QuantityValue quantity={value} /> : 'Not specified by the user'}</dd>
              </div>
            ))}
          </dl>
        </details>
      </Panel>
      {oldContext && (
        <Notice tone="warning">
          This answer uses an earlier workspace snapshot:{' '}
          <strong>{answer.scenario_snapshot?.name ?? 'No scenario'}</strong>. Current context:{' '}
          <strong>{workspace.scenario?.name ?? 'No scenario'}</strong>. Saving and exporting will
          preserve the original conditions.
          <div style={{ marginTop: 12 }}>
            <Button variant="secondary" onClick={() => onAsk(answer.question)}>
              Prepare a new question in the current context
            </Button>
          </div>
        </Notice>
      )}
      {answer.status === 'insufficient_evidence' && (
        <Notice tone="warning">
          There is not enough evidence for a complete answer. Available observations, gaps and
          follow-up questions are shown below.
        </Notice>
      )}
      {answer.status === 'conflicting_evidence' && (
        <Notice tone="warning">
          The evidence conflicts. Compare conditions and methods before combining findings.
        </Notice>
      )}
      <div className={s.layout}>
        <AnswerBlocks answer={answer} onEvidence={setEvidenceId} />
        <aside className={s.sources} aria-label="Answer evidence">
          <h3>
            <FileText size={16} /> Answer evidence
          </h3>
          {answer.citations.map((citation, index) => (
            <button key={citation.evidence_id} onClick={() => setEvidenceId(citation.evidence_id)}>
              <span>[{index + 1}]</span>
              <div>
                <strong>{citation.label}</strong>
                <small>
                  {[
                    citation.locator.row_key,
                    citation.locator.page ? `p. ${citation.locator.page}` : null,
                    citation.locator.section,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </small>
              </div>
              <ArrowUpRight size={12} />
            </button>
          ))}
          <p>Links open registered sources. Free-form answer text is never used as a link.</p>
        </aside>
      </div>
      {answer.limitations.length > 0 && (
        <Panel className={s.limitations}>
          <h3>Limits of the answer</h3>
          <ul>
            {answer.limitations.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </Panel>
      )}
      <ApplicabilityView
        result={answer.applicability}
        partial={['partial', 'simulated_partial'].includes(
          answer.scenario_snapshot?.gravity_regime ?? '',
        )}
        onEvidence={setEvidenceId}
      />
      {answer.follow_up_questions.length > 0 && (
        <div className={s.followup}>
          <h3>Questions to explore next</h3>
          {answer.follow_up_questions.map((question) => (
            <button className="textLink" key={question} onClick={() => onAsk(question)}>
              {question} <ArrowUpRight size={13} />
            </button>
          ))}
        </div>
      )}
      <details className={s.audit}>
        <summary>Versions and validation</summary>
        <p>
          Retrieval: {answer.retrieval_mode} · reasoning: {answer.reasoning_revision}
        </p>
        <p>The API reports that the schema, citations, numbers and scope have been validated.</p>
      </details>
      <EvidenceDrawer
        id={evidenceId}
        revision={answer.data_revision}
        onClose={() => setEvidenceId(null)}
      />
    </section>
  );
}
