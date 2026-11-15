import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  Bookmark,
  Check,
  GitCompareArrows,
  Search,
  SlidersHorizontal,
  X,
  CheckCircle2,
} from 'lucide-react';
import { api } from '../api/client';
import { useInvestigationOptions } from '../api/hooks';
import type { Schema } from '../api/types';
import { useWorkspace } from '../state/WorkspaceProvider';
import { Badge, Button, EmptyState, Loading, Notice, PageHeader, Panel } from '../components/ui';
import { ErrorState } from '../components/ErrorState';
import { Drawer } from '../components/Drawer';
import { parseCatalog, rangeKeys } from './catalogParams';
import s from './Catalog.module.css';

export function Catalog() {
  const { workspace, config, toggleComparison, toggleSaved, pending } = useWorkspace();
  const options = useInvestigationOptions();
  const [params, setParams] = useSearchParams();
  const [draft, setDraft] = useState(params.get('q') ?? '');
  const [mobileFilters, setMobileFilters] = useState(false);
  useEffect(() => setDraft(params.get('q') ?? ''), [params]);
  const parsed = parseCatalog(params, workspace.data_revision, workspace.scenario);
  const results = useQuery({
    queryKey: ['search', parsed.request],
    queryFn: ({ signal }) => api.search(parsed.request, signal).then((r) => r.data),
    enabled: !parsed.error,
  });
  function set(name: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value === null || value === '') next.delete(name);
    else next.set(name, value);
    next.delete('cursor');
    setParams(next);
  }
  function toggle(name: string, value: string) {
    const selected = params.getAll(name);
    const next = new URLSearchParams(params);
    next.delete(name);
    for (const item of selected.includes(value)
      ? selected.filter((v) => v !== value)
      : [...selected, value])
      next.append(name, item);
    next.delete('cursor');
    setParams(next);
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    set('q', draft.trim());
  }
  const groups = [
    { name: 'scope', label: 'Направление', options: config.dictionaries.scope },
    {
      name: 'investigation',
      label: 'Исследование',
      options: (options.data ?? []).map((i) => ({ value: i.id, label: i.acronym })),
    },
    { name: 'fuel', label: 'Состояние топлива', options: config.dictionaries.fuel_state },
    {
      name: 'material',
      label: 'Материал',
      options: config.dictionaries.materials.map((m) => ({ value: m.value, label: m.label })),
    },
    { name: 'gravity', label: 'Гравитация', options: config.dictionaries.gravity_regime },
  ];
  const filters = (
    <div className={s.filterContents}>
      <div className="spaceBetween">
        <h2>Условия поиска</h2>
        <button className="textLink" onClick={() => setParams(new URLSearchParams())}>
          Сбросить
        </button>
      </div>
      {groups.map((group, index) => (
        <details key={group.name} open={index === 0 || index === 2}>
          <summary>
            {group.label}
            {params.getAll(group.name).length > 0 && (
              <span>{params.getAll(group.name).length}</span>
            )}
          </summary>
          <div className={s.checkboxGroup}>
            {group.options.map((option) => (
              <label className="checkLabel" key={option.value}>
                <input
                  type="checkbox"
                  checked={params.getAll(group.name).includes(option.value)}
                  onChange={() => toggle(group.name, option.value)}
                />
                {option.label}
              </label>
            ))}
          </div>
        </details>
      ))}
      {rangeKeys.map((range) => (
        <fieldset className={s.range} key={range.prefix}>
          <legend>
            {range.name} <span>{range.label}</span>
          </legend>
          <div>
            {(['min', 'max'] as const).map((bound) => (
              <label className="field" key={bound}>
                <span>{bound === 'min' ? 'От' : 'До'}</span>
                <input
                  type="number"
                  min="0"
                  max={range.max}
                  step="any"
                  aria-label={`${range.name} ${bound === 'min' ? 'минимум' : 'максимум'}, ${range.label}`}
                  value={
                    params.get(`${range.prefix}_${bound}`) === null
                      ? ''
                      : Number(
                          (
                            Number(params.get(`${range.prefix}_${bound}`)) * range.factor
                          ).toPrecision(10),
                        )
                  }
                  onChange={(event) =>
                    set(
                      `${range.prefix}_${bound}`,
                      event.target.value === ''
                        ? null
                        : String(Number(event.target.value) / range.factor),
                    )
                  }
                />
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      <label className="field">
        Наличие измерений
        <select
          value={params.get('measurements') ?? ''}
          onChange={(e) => set('measurements', e.target.value || null)}
        >
          <option value="">Любое</option>
          <option value="true">Есть измерения</option>
          <option value="false">Нет измерений</option>
        </select>
      </label>
      <label className="checkLabel">
        <input
          type="checkbox"
          checked={params.get('unknown') === 'true'}
          onChange={(e) => set('unknown', e.target.checked ? 'true' : null)}
        />
        Включать неизвестные значения
      </label>
      <p className="tiny muted">Неизвестное значение не отменяет остальные заданные ограничения.</p>
    </div>
  );
  const data = results.data;
  const renderItem = (item: Schema['SearchItem']) => {
    const inv = item.investigation;
    const compared = workspace.selected_investigation_ids.includes(inv.id);
    const saved = workspace.saved_investigation_ids.includes(inv.id);
    return (
      <article className={s.result} key={inv.id}>
        <div className={s.resultTop}>
          <div className="inline">
            <span className={s.psi}>{inv.psi_id}</span>
            <Badge tone={item.related ? 'cyan' : 'teal'}>
              {item.related ? 'Связанная работа' : 'Прямое соответствие'}
            </Badge>
          </div>
          <button
            className="iconButton"
            aria-label={`${saved ? 'Убрать из сохранённых' : 'Сохранить'} ${inv.acronym}`}
            aria-pressed={saved}
            disabled={pending}
            onClick={() => void toggleSaved(inv.id)}
          >
            <Bookmark size={17} fill={saved ? 'currentColor' : 'none'} />
          </button>
        </div>
        <Link to={`/investigations/${inv.id}`} className={s.resultTitle}>
          <h2>{inv.acronym}</h2>
          <ArrowRight size={18} />
        </Link>
        <p className={s.resultDescription}>{inv.title}</p>
        <div className={s.chips}>
          {inv.fuel_states.map((state) => (
            <Badge key={state}>
              {config.dictionaries.fuel_state.find((f) => f.value === state)?.label ?? state}
            </Badge>
          ))}
          {inv.gravity_regimes.map((regime) => (
            <Badge key={regime}>
              {config.dictionaries.gravity_regime.find((g) => g.value === regime)?.label ?? regime}
            </Badge>
          ))}
        </div>
        <div className={s.reasons}>
          {item.match_reasons.map((reason) => (
            <p key={`${reason.code}:${reason.field}`}>
              <CheckCircle2 size={14} />
              {reason.text}
            </p>
          ))}
          {item.differences.map((text) => (
            <p className={s.difference} key={`${text.code}:${text.field}`}>
              {text.text}
            </p>
          ))}
          {item.missing_fields.map((text) => (
            <p className={s.missing} key={text}>
              {text}
            </p>
          ))}
        </div>
        <div className={s.resultFooter}>
          <Link className="textLink" to={`/investigations/${inv.id}`}>
            Открыть условия и основания <ArrowRight size={13} />
          </Link>
          <Button
            variant="ghost"
            disabled={pending}
            aria-pressed={compared}
            onClick={() => void toggleComparison(inv.id)}
          >
            {compared ? <Check size={14} /> : <GitCompareArrows size={14} />}{' '}
            {compared ? 'В сравнении' : 'Сравнить'}
          </Button>
        </div>
      </article>
    );
  };
  return (
    <>
      <PageHeader
        eyebrow="КАТАЛОГ / NASA PSI"
        title="Исследования"
        description="Найдите работы под свою задачу. Причины соответствия и различия видны рядом с результатом."
        action={
          <Link className="textLink" to="/compare">
            Сравнение · {workspace.selected_investigation_ids.length}/3 <ArrowRight size={14} />
          </Link>
        }
      />
      <form className={s.search} onSubmit={submit}>
        <Search size={19} />
        <label className="srOnly" htmlFor="catalog-query">
          Поисковый вопрос
        </label>
        <input
          id="catalog-query"
          value={draft}
          maxLength={config.limits.question_chars_max}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Вопрос, материал или название исследования"
        />
        <Button type="submit">Найти</Button>
      </form>
      <div className={s.catalog}>
        <Panel className={s.filters}>{filters}</Panel>
        <div className={s.results}>
          <div className={s.toolbar}>
            <div className="inline">
              <Button
                className={s.mobileFilterButton}
                variant="secondary"
                onClick={() => setMobileFilters(true)}
              >
                <SlidersHorizontal size={15} /> Фильтры
              </Button>
              <span className={s.resultCount} role="status">
                {results.isFetching ? 'Обновляем выдачу…' : `Исследований: ${data?.total ?? '—'}`}
              </span>
            </div>
            <label className={s.sort}>
              Сортировка
              <select
                value={params.get('sort') ?? 'relevance'}
                onChange={(e) => set('sort', e.target.value)}
              >
                <option value="relevance">По соответствию</option>
                <option value="acronym">По названию</option>
              </select>
            </label>
          </div>
          <div className={s.searchMode}>
            <span className={s.statusDot} />
            {data?.retrieval_mode === 'hybrid'
              ? 'Текстовый и семантический поиск'
              : 'Поиск по тексту и фильтрам'}
            <span>Ревизия {workspace.data_revision}</span>
          </div>
          {parsed.error && <Notice tone="error">{parsed.error}</Notice>}
          {results.isPending && !parsed.error ? (
            <Loading />
          ) : results.isError ? (
            <ErrorState
              error={results.error}
              onRetry={() => {
                set('cursor', null);
                void results.refetch();
              }}
            />
          ) : (
            data && (
              <>
                {data.items.filter((item) => !item.related).map(renderItem)}
                {data.items.some((item) => item.related) && (
                  <>
                    <h2 className={s.relatedTitle}>Связанные работы</h2>
                    <p className="tiny muted">
                      Эти работы отличаются от вопроса; заданные жёсткие фильтры сохраняются.
                    </p>
                    {data.items.filter((item) => item.related).map(renderItem)}
                  </>
                )}
                {!data.items.length && (
                  <EmptyState
                    title="Нет исследований с такими условиями"
                    action={
                      <Button variant="secondary" onClick={() => set('related', 'true')}>
                        Показать связанные материалы
                      </Button>
                    }
                  >
                    Ограничения сохранены. Измените диапазон или явно включите связанные работы.
                    Пустая выдача не означает безопасность.
                  </EmptyState>
                )}
                <div className={s.pagination}>
                  {params.has('cursor') && (
                    <Button variant="ghost" onClick={() => set('cursor', null)}>
                      К началу выдачи
                    </Button>
                  )}
                  {data.next_cursor && (
                    <Button
                      variant="secondary"
                      onClick={() => {
                        const next = new URLSearchParams(params);
                        next.set('cursor', data.next_cursor!);
                        setParams(next);
                      }}
                    >
                      Следующая страница <ArrowRight size={14} />
                    </Button>
                  )}
                </div>
              </>
            )
          )}
          <label className={s.relatedToggle}>
            <input
              type="checkbox"
              checked={params.get('related') === 'true'}
              onChange={(e) => set('related', e.target.checked ? 'true' : null)}
            />
            Показывать связанные работы отдельной группой
          </label>
        </div>
      </div>
      <Drawer
        open={mobileFilters}
        onOpenChange={setMobileFilters}
        title="Фильтры исследований"
        description="Условия применяются к текущему поиску и сохраняются в адресе страницы."
      >
        {filters}
        <Button onClick={() => setMobileFilters(false)}>
          <X size={14} /> Закрыть фильтры
        </Button>
      </Drawer>
    </>
  );
}
