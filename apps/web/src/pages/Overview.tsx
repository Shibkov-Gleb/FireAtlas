import { IS_DEMO } from '../lib/env';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  BookOpen,
  ChartScatter,
  Check,
  Flame,
  Search,
  ShieldCheck,
  ScanEye,
  Wind,
  ExternalLink,
} from 'lucide-react';
import { api } from '../api/client';
import { emptyFilters, type Schema } from '../api/types';
import { useWorkspace } from '../state/WorkspaceProvider';
import { Badge, Button, Loading, Panel } from '../components/ui';
import { ErrorState } from '../components/ErrorState';
import s from './Overview.module.css';

const directions = [
  {
    value: 'prevention',
    label: 'Prevention',
    description: 'Materials and combustion conditions',
    icon: ShieldCheck,
    color: 'orange',
  },
  {
    value: 'detection',
    label: 'Detection',
    description: 'Smoke and detector sensitivity',
    icon: ScanEye,
    color: 'cyan',
  },
  {
    value: 'suppression',
    label: 'Suppression',
    description: 'Extinction and suppressants',
    icon: Wind,
    color: 'purple',
  },
] as const;

export function Overview() {
  const { workspace, config } = useWorkspace();
  const navigate = useNavigate();
  const [question, setQuestion] = useState('');
  const [direction, setDirection] = useState<Schema['Scope'] | null>(null);
  const [error, setError] = useState('');
  const starter = useQuery({
    queryKey: ['starter', workspace.data_revision],
    queryFn: ({ signal }) =>
      api
        .search(
          {
            query: '',
            sort: 'acronym',
            locale: 'en',
            data_revision: workspace.data_revision,
            filters: { ...emptyFilters(), scopes: ['prevention', 'detection', 'suppression'] },
            scenario: null,
            include_related: false,
            cursor: null,
            limit: 3,
          },
          signal,
        )
        .then((r) => r.data),
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    const value = question.trim();
    if (!direction && value.length < 3) {
      setError('Enter a question of at least 3 characters or select a research area.');
      return;
    }
    if (value.length > config.limits.question_chars_max) {
      setError(`Maximum question length: ${config.limits.question_chars_max} characters.`);
      return;
    }
    const params = new URLSearchParams();
    if (value) params.set('q', value);
    if (direction) params.set('scope', direction);
    navigate(`/investigations?${params}`);
  }
  return (
    <div className={s.overview}>
      <div className={s.welcome}>
        <div className={s.eyebrow}>
          <span /> NASA SPACE APPS · FLAME IN FREEFALL
        </div>
        <Badge tone="teal">NASA PSI open sources</Badge>
      </div>
      <section className={s.hero} aria-labelledby="overview-title">
        <div className={s.heroContent}>
          <div className={s.kicker}>MICROGRAVITY. MEASUREMENTS. EVIDENCE.</div>
          <h1 id="overview-title">
            Understand fire
            <br />
            <span>in microgravity.</span>
          </h1>
          <p>
            Find NASA research, explore test conditions and trace every finding to its original
            source.
          </p>
          <div className={s.heroPoints}>
            <span>
              <Check size={12} /> From question to source
            </span>
            <span>
              <Check size={12} /> With mission conditions in mind
            </span>
          </div>
        </div>
        <div className={s.orbitGraphic} aria-hidden="true">
          <div className={s.orbitOuter} />
          <div className={s.orbitMiddle} />
          <div className={s.orbitInner} />
          <div className={s.core}>
            <Flame size={49} strokeWidth={1.3} />
          </div>
          <span className={s.orbitPointOne} />
          <span className={s.orbitPointTwo} />
          <span className={s.graphLabelOne}>g ≈ μg</span>
          <span className={s.graphLabelTwo}>COMBUSTION SCIENCE</span>
          <span className={s.crossOne}>+</span>
          <span className={s.crossTwo}>+</span>
        </div>
      </section>
      <form className={s.questionPanel} onSubmit={submit}>
        <div className="spaceBetween">
          <h2 className="sectionTitle">What do you want to explore?</h2>
          <span className={s.stepLabel}>01 / DEFINE THE QUESTION</span>
        </div>
        <div className={s.searchRow}>
          <Search size={20} />
          <label className="srOnly" htmlFor="overview-question">
            Your research question
          </label>
          <input
            id="overview-question"
            value={question}
            onChange={(event) => {
              setQuestion(event.target.value);
              setError('');
            }}
            placeholder="How does ventilation affect the combustion of solid materials?"
            maxLength={config.limits.question_chars_max}
            aria-invalid={!!error}
            aria-describedby={error ? 'overview-error' : 'overview-hint'}
          />
          <Button type="submit">
            Explore <ArrowRight size={16} />
          </Button>
        </div>
        {error && (
          <p className="errorText" id="overview-error" role="alert">
            {error}
          </p>
        )}
        <p id="overview-hint" className={s.searchHint}>
          Start with your question or select a research area. Searching does not start AI
          generation.
        </p>
        <div className={s.directions}>
          {directions.map(({ value, label, description, icon: Icon, color }) => (
            <button
              type="button"
              key={value}
              aria-pressed={direction === value}
              onClick={() => setDirection(direction === value ? null : value)}
              className={`${s.direction} ${s[color]} ${direction === value ? s.selected : ''}`}
            >
              <span className={s.directionIcon}>
                <Icon size={20} strokeWidth={1.6} />
              </span>
              <span>
                <strong>{label}</strong>
                <small>{description}</small>
              </span>
              <ArrowRight size={14} />
            </button>
          ))}
        </div>
      </form>
      <section>
        <div className={s.sectionHeading}>
          <div>
            <span className={s.miniLabel}>START EXPLORING</span>
            <h2>Three research areas</h2>
          </div>
          <Link className="textLink" to="/investigations">
            Open catalog <ArrowRight size={14} />
          </Link>
        </div>
        {starter.isPending ? (
          <Loading />
        ) : starter.isError ? (
          <ErrorState error={starter.error} onRetry={() => void starter.refetch()} />
        ) : (
          <div className={s.investigations}>
            {starter.data.items.map(({ investigation: inv }, index) => (
              <Link key={inv.id} to={`/investigations/${inv.id}`} className={s.researchCard}>
                <div className="spaceBetween">
                  <span className={`${s.researchIcon} ${s[directions[index]?.color ?? 'cyan']}`}>
                    {index === 0 ? (
                      <Flame size={20} />
                    ) : index === 1 ? (
                      <ChartScatter size={20} />
                    ) : (
                      <ScanEye size={20} />
                    )}
                  </span>
                  <span className={s.psi}>{inv.psi_id}</span>
                </div>
                <div className={s.researchTitle}>
                  <h3>{inv.acronym}</h3>
                  <ArrowRight size={16} />
                </div>
                <p>{inv.title}</p>
                <div className={s.researchFooter}>
                  <span>Microgravity</span>
                  <span>
                    NASA PSI <ExternalLink size={10} />
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
      <Panel className={s.evidencePanel}>
        <span className={s.evidenceIcon}>
          <BookOpen size={22} strokeWidth={1.4} />
        </span>
        <div>
          <h2>Every finding has evidence</h2>
          <p>
            Check the test run, original record and limitations. Missing data does not establish
            safety.
          </p>
        </div>
        <Link className="textLink" to="/measurements">
          Explore measurements <ArrowRight size={14} />
        </Link>
      </Panel>
      {IS_DEMO && (
        <p className={s.demoNote}>
          Demo mode · prepared interface examples · scientific acceptance of the corpus is performed
          separately.
        </p>
      )}
    </div>
  );
}
