import type { Schema } from '../api/types';
import { Badge, Notice } from './ui';
import s from './ApplicabilityView.module.css';

const labels = {
  match: 'Matches',
  mismatch: 'Differs',
  unknown: 'Unknown',
  not_covered: 'No direct evidence',
} as const;
const fieldLabels: Record<string, string> = {
  safety_task: 'Task',
  smoke_measurement: 'Smoke measurements',
  joint_conditions: 'Combined conditions',
  gravity_regime: 'Gravity',
  oxygen_fraction: 'Oxygen fraction',
  pressure: 'Pressure',
  airflow_speed: 'Airflow speed',
  geometry: 'Geometry',
  material_ids: 'Material',
};
export function ApplicabilityView({
  result,
  partial = false,
  onEvidence,
}: {
  result: Schema['ApplicabilityResult'] | null | undefined;
  partial?: boolean;
  onEvidence?: (id: string) => void;
}) {
  if (!result) return <Notice>Select a mission scenario to assess applicability.</Notice>;
  return (
    <section className={s.section}>
      <div className="spaceBetween">
        <h2 className="sectionTitle">Applicability to conditions</h2>
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
            ? 'Transfer requires justification'
            : result.overall === 'direct_evidence'
              ? 'Direct evidence available'
              : result.overall === 'related_evidence'
                ? 'Related evidence'
                : 'Insufficient evidence'}
        </Badge>
      </div>
      {partial && (
        <Notice tone="warning">
          <strong>PSI contains no direct partial-gravity measurements.</strong> Related findings are
          considered with explicit limitations; selecting a mission does not create missing
          measurements.
        </Notice>
      )}
      <div className="tableScroll" role="region" tabIndex={0} aria-label="Applicability factors">
        <table>
          <thead>
            <tr>
              <th scope="col">Factor</th>
              <th scope="col">Status</th>
              <th scope="col">Evidence and limitations</th>
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
                        Evidence {index + 1}
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
          <h3>What still needs to be checked</h3>
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
