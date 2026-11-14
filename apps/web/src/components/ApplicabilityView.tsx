import type { Schema } from '../api/types';
import { Badge, Notice } from './ui';
import s from './ApplicabilityView.module.css';

const labels = {
  match: 'Совпадает',
  mismatch: 'Отличается',
  unknown: 'Неизвестно',
  not_covered: 'Прямых данных нет',
} as const;
const fieldLabels: Record<string, string> = {
  gravity_regime: 'Гравитация',
  oxygen_fraction: 'Доля кислорода',
  pressure: 'Давление',
  airflow_speed: 'Скорость воздуха',
  geometry: 'Геометрия',
  material_ids: 'Материал',
};
export function ApplicabilityView({
  result,
  partial = false,
  onEvidence,
}: {
  result: Schema['ApplicabilityResult'];
  partial?: boolean;
  onEvidence?: (id: string) => void;
}) {
  return (
    <section className={s.section}>
      <div className="spaceBetween">
        <h2 className="sectionTitle">Применимость к условиям</h2>
        <Badge
          tone={
            partial || result.overall === 'insufficient_evidence'
              ? 'orange'
              : result.overall === 'direct_evidence'
                ? 'teal'
                : 'cyan'
          }
        >
          {partial
            ? 'Перенос требует обоснования'
            : result.overall === 'direct_evidence'
              ? 'Есть прямые основания'
              : result.overall === 'related_evidence'
                ? 'Связанные основания'
                : 'Недостаточно доказательств'}
        </Badge>
      </div>
      {partial && (
        <Notice tone="warning">
          <strong>Прямых данных частичной гравитации в PSI нет.</strong> Связанные результаты
          изучаются с явными ограничениями; выбор миссии не создаёт отсутствующие измерения.
        </Notice>
      )}
      <div className="tableScroll" role="region" tabIndex={0} aria-label="Факторы применимости">
        <table>
          <thead>
            <tr>
              <th scope="col">Фактор</th>
              <th scope="col">Статус</th>
              <th scope="col">Основание и ограничения</th>
            </tr>
          </thead>
          <tbody>
            {result.factors.map((factor) => (
              <tr key={factor.field}>
                <th scope="row">{fieldLabels[factor.field] ?? factor.field}</th>
                <td>
                  <Badge
                    tone={
                      factor.status === 'match'
                        ? 'teal'
                        : factor.status === 'unknown'
                          ? 'neutral'
                          : 'orange'
                    }
                  >
                    {labels[factor.status]}
                  </Badge>
                </td>
                <td>
                  {factor.explanation}
                  <div className="inline" style={{ marginTop: 8 }}>
                    {factor.evidence_ids.map((id, index) => (
                      <button key={id} className="textLink" onClick={() => onEvidence?.(id)}>
                        Основание {index + 1}
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.gaps.length > 0 && (
        <div className={s.gaps}>
          <h3>Что ещё требуется проверить</h3>
          {result.gaps.map((gap, index) => (
            <div key={index}>
              <p>{gap.description}</p>
              <span>{gap.suggested_next_step}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
