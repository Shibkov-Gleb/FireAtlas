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
  summary: 'Краткий ответ',
  observation: 'Наблюдение',
  synthesis: 'Обобщение',
  limitation: 'Ограничение',
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
                    {citation?.label ?? 'Основание'} <ArrowUpRight size={11} />
                  </button>
                );
              })}
            </div>
          )}
          {block.quantities.length > 0 && (
            <details className={s.quantities}>
              <summary>Числа и исходные значения</summary>
              {block.quantities.map((entry, index) => (
                <div key={index}>
                  <span>
                    {{
                      burn_duration: 'Время горения',
                      initial_diameter: 'Начальный диаметр',
                      pressure: 'Давление',
                    }[entry.name as 'burn_duration'] ?? entry.name}
                  </span>
                  <QuantityValue quantity={entry.quantity} />
                  {entry.evidence_ids.map((id) => (
                    <button className="textLink" key={id} onClick={() => onEvidence(id)}>
                      Исходная строка
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
  if (query.isPending) return <Loading>Открываем результат…</Loading>;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const answer = query.data;
  if (!Object.values(answer.validation_summary).every(Boolean))
    return (
      <Notice tone="error">Ответ не прошёл обязательную проверку. Текст не опубликован.</Notice>
    );
  const oldContext = answer.workspace_revision !== workspace.revision;
  const saved = workspace.saved_answer_ids.includes(answer.id);
  return (
    <section className={s.answer}>
      <div className="spaceBetween">
        <div className="inline">
          <Badge tone={answer.status === 'answered' ? 'teal' : 'orange'}>
            {answer.status === 'answered'
              ? 'Ответ готов'
              : answer.status === 'insufficient_evidence'
                ? 'Недостаточно доказательств'
                : 'Есть противоречия'}
          </Badge>
          {IS_DEMO && (
            <Badge tone="purple">
              <Sparkles size={12} /> Подготовленный пример
            </Badge>
          )}
        </div>
        <Button
          variant="secondary"
          disabled={pending || saved}
          onClick={() =>
            void saveAnswer(answer.id).then((ok) => {
              if (ok) notify('Ответ сохранён вместе с исходным контекстом.');
            })
          }
        >
          {saved ? <Check size={14} /> : <Bookmark size={14} />}{' '}
          {saved ? 'Ответ сохранён' : 'Сохранить ответ'}
        </Button>
      </div>
      <Panel className={s.context}>
        <h2>Контекст ответа: {answer.scenario_snapshot?.name ?? 'Без сценария'}</h2>
        <p>{answer.question}</p>
        <div className={s.metadata}>
          <span>{formatDate(answer.created_at)}</span>
          <span>Пространство: {answer.workspace_revision}</span>
          <span>Корпус: {answer.data_revision}</span>
        </div>
        <details>
          <summary>Зафиксированные условия</summary>
          <dl>
            <div>
              <dt>Гравитация</dt>
              <dd>{answer.scenario_snapshot?.gravity_regime}</dd>
            </div>
            {(
              [
                ['Кислород', answer.scenario_snapshot?.oxygen_fraction],
                ['Давление', answer.scenario_snapshot?.pressure],
                ['Скорость воздуха', answer.scenario_snapshot?.airflow_speed],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value ? <QuantityValue quantity={value} /> : 'Не задано пользователем'}</dd>
              </div>
            ))}
          </dl>
        </details>
      </Panel>
      {oldContext && (
        <Notice tone="warning">
          Ответ получен на предыдущем снимке пространства:{' '}
          <strong>{answer.scenario_snapshot?.name ?? 'Без сценария'}</strong>. Текущий контекст:{' '}
          <strong>{workspace.scenario?.name ?? 'Без сценария'}</strong>. Сохранение и отчёт сохранят
          исходные условия.
          <div style={{ marginTop: 12 }}>
            <Button variant="secondary" onClick={() => onAsk(answer.question)}>
              Подготовить новый вопрос в текущем контексте
            </Button>
          </div>
        </Notice>
      )}
      {answer.status === 'insufficient_evidence' && (
        <Notice tone="warning">
          Данных недостаточно для полного ответа. Ниже показаны доступные наблюдения, пробелы и
          уточняющие вопросы.
        </Notice>
      )}
      {answer.status === 'conflicting_evidence' && (
        <Notice tone="warning">
          Основания расходятся. Сравните условия и методики, прежде чем объединять выводы.
        </Notice>
      )}
      <div className={s.layout}>
        <AnswerBlocks answer={answer} onEvidence={setEvidenceId} />
        <aside className={s.sources} aria-label="Основания ответа">
          <h3>
            <FileText size={16} /> Основания ответа
          </h3>
          {answer.citations.map((citation, index) => (
            <button key={citation.evidence_id} onClick={() => setEvidenceId(citation.evidence_id)}>
              <span>[{index + 1}]</span>
              <div>
                <strong>{citation.label}</strong>
                <small>
                  {[
                    citation.locator.row_key,
                    citation.locator.page ? `Стр. ${citation.locator.page}` : null,
                    citation.locator.section,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </small>
              </div>
              <ArrowUpRight size={12} />
            </button>
          ))}
          <p>
            Ссылки ведут к зарегистрированным источникам. Свободный текст ответа не используется как
            ссылка.
          </p>
        </aside>
      </div>
      {answer.limitations.length > 0 && (
        <Panel className={s.limitations}>
          <h3>Границы вывода</h3>
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
          <h3>Что уточнить дальше</h3>
          {answer.follow_up_questions.map((question) => (
            <button className="textLink" key={question} onClick={() => onAsk(question)}>
              {question} <ArrowUpRight size={13} />
            </button>
          ))}
        </div>
      )}
      <details className={s.audit}>
        <summary>Версии и проверка ответа</summary>
        <p>
          Поиск: {answer.retrieval_mode} · reasoning: {answer.reasoning_revision}
        </p>
        <p>Схема, ссылки, числа и область вывода проверены согласно ответу API.</p>
      </details>
      <EvidenceDrawer
        id={evidenceId}
        revision={answer.data_revision}
        onClose={() => setEvidenceId(null)}
      />
    </section>
  );
}
