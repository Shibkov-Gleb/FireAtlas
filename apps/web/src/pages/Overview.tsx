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
    label: 'Предотвращение',
    description: 'Материалы и условия горения',
    icon: ShieldCheck,
    color: 'orange',
  },
  {
    value: 'detection',
    label: 'Обнаружение',
    description: 'Дым и чувствительность датчиков',
    icon: ScanEye,
    color: 'cyan',
  },
  {
    value: 'suppression',
    label: 'Подавление',
    description: 'Погасание и подавляющие газы',
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
            locale: 'ru',
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
      setError('Введите вопрос от 3 символов или выберите направление.');
      return;
    }
    if (value.length > config.limits.question_chars_max) {
      setError(`Максимальная длина вопроса — ${config.limits.question_chars_max} символов.`);
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
        <Badge tone="teal">Открытые источники NASA PSI</Badge>
      </div>
      <section className={s.hero} aria-labelledby="overview-title">
        <div className={s.heroContent}>
          <div className={s.kicker}>МИКРОГРАВИТАЦИЯ. ИЗМЕРЕНИЯ. ДОКАЗАТЕЛЬСТВА.</div>
          <h1 id="overview-title">
            Понять огонь
            <br />
            <span>в невесомости.</span>
          </h1>
          <p>
            Находите исследования NASA, изучайте условия опытов и проверяйте каждый вывод по
            первоисточнику.
          </p>
          <div className={s.heroPoints}>
            <span>
              <Check size={12} /> От вопроса к источнику
            </span>
            <span>
              <Check size={12} /> С учётом условий миссии
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
          <h2 className="sectionTitle">Что вы хотите выяснить?</h2>
          <span className={s.stepLabel}>01 / ПОСТАНОВКА ЗАДАЧИ</span>
        </div>
        <div className={s.searchRow}>
          <Search size={20} />
          <label className="srOnly" htmlFor="overview-question">
            Ваш вопрос об исследованиях
          </label>
          <input
            id="overview-question"
            value={question}
            onChange={(event) => {
              setQuestion(event.target.value);
              setError('');
            }}
            placeholder="Как вентиляция влияет на горение твёрдых материалов?"
            maxLength={config.limits.question_chars_max}
            aria-invalid={!!error}
            aria-describedby={error ? 'overview-error' : 'overview-hint'}
          />
          <Button type="submit">
            Исследовать <ArrowRight size={16} />
          </Button>
        </div>
        {error && (
          <p className="errorText" id="overview-error" role="alert">
            {error}
          </p>
        )}
        <p id="overview-hint" className={s.searchHint}>
          Начните со своего вопроса или выберите направление. Поиск не запускает генерацию AI.
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
            <span className={s.miniLabel}>НАЧНИТЕ ЗНАКОМСТВО</span>
            <h2>Три направления исследований</h2>
          </div>
          <Link className="textLink" to="/investigations">
            Открыть каталог <ArrowRight size={14} />
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
                  <span>Микрогравитация</span>
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
          <h2>У каждого вывода есть основание</h2>
          <p>
            Проверяйте опыт, исходную строку и ограничения. Отсутствие данных не означает
            безопасность.
          </p>
        </div>
        <Link className="textLink" to="/measurements">
          Изучить измерения <ArrowRight size={14} />
        </Link>
      </Panel>
      {IS_DEMO && (
        <p className={s.demoNote}>
          Демонстрационный режим · подготовленные примеры интерфейса · научная приёмка корпуса
          выполняется отдельно.
        </p>
      )}
    </div>
  );
}
