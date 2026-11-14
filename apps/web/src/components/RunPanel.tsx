import { useQuery } from '@tanstack/react-query';
import { X, ArrowUpRight } from 'lucide-react';
import { api } from '../api/client';
import type { Quantity } from '../api/types';
import { formatQuantity, geometryLabels, outcomeLabels, statusLabels } from '../lib/format';
import { useWorkspace } from '../state/WorkspaceProvider';
import { Badge, EmptyState, Loading, Notice, Panel } from './ui';
import { ErrorState } from './ErrorState';
import s from './RunPanel.module.css';

export function QuantityValue({quantity,expectedUnit,compact=false}:{quantity:Quantity;expectedUnit?:Quantity['unit'];compact?:boolean}){
  const text=formatQuantity(quantity,expectedUnit);
  if(compact)return <span title={quantity.raw_value===null?statusLabels[quantity.status]:`Источник: ${quantity.raw_value} ${quantity.raw_unit??''}`}>{text}</span>;
  return <div className={s.quantity}><span className={quantity.value===null?s.unknown:''}>{text}</span>{quantity.status==='derived'&&<small>Вычислено · {quantity.derivation?.formula_id}</small>}{quantity.raw_value!==null&&<details><summary>Исходное значение</summary><div>{quantity.raw_value} {quantity.raw_unit??''}<br/><span>{statusLabels[quantity.status]}</span></div></details>}</div>;
}
export function RunPanel({runId,revision,onEvidence,onClose,investigationId}:{runId:string|null;revision:string;onEvidence:(id:string)=>void;onClose?:()=>void;investigationId?:string}){
  const {config}=useWorkspace();
  const query=useQuery({queryKey:['run',runId,revision],queryFn:({signal})=>api.run(runId!,revision,signal).then(r=>r.data),enabled:!!runId,staleTime:Infinity});
  if(!runId)return <EmptyState title="Выберите опыт">Нажмите на запись в таблице или точку графика, чтобы увидеть условия.</EmptyState>;
  if(query.isPending)return <Panel><Loading/></Panel>;if(query.isError)return <ErrorState error={query.error} onRetry={()=>void query.refetch()}/>;
  const run=query.data;
  if(investigationId&&run.investigation_id!==investigationId)return <Notice tone="warning">Выбранная запись относится к другому исследованию.</Notice>;
  const conditions=[['Доля кислорода',run.conditions.oxygen_fraction,'fraction'],['Общее давление',run.conditions.pressure,'Pa'],['Калиброванная скорость',run.conditions.airflow_speed,'m_s'],['Температура',run.conditions.ambient_temperature,'K'],['Уровень гравитации',run.conditions.gravity_level,'g_fraction']] as const;
  return <Panel className={s.panel}><div className="spaceBetween"><span className={s.label}>ВЫБРАННЫЙ ОПЫТ</span>{onClose&&<button className="iconButton" onClick={onClose} aria-label="Снять выбор опыта"><X size={16}/></button>}</div><h2 data-testid="selected-run-id">{run.source_test_id}</h2><div className="inline"><Badge tone={run.terminal_outcome.category==='disruption'?'orange':'cyan'}>{outcomeLabels[run.terminal_outcome.category]}</Badge></div><p className={s.rawOutcome}>Исход источника: <span>{run.terminal_outcome.raw_label}</span></p><div className={s.section}><h3>Образец</h3><dl><div><dt>Материал</dt><dd>{config.dictionaries.materials.find(m=>m.id===run.material_id)?.label??'Не сообщено'}</dd></div><div><dt>Геометрия</dt><dd>{geometryLabels[run.sample.geometry]}</dd></div><div><dt>Начальный диаметр</dt><dd><QuantityValue quantity={run.sample.initial_diameter} expectedUnit="m"/></dd></div><div><dt>Толщина</dt><dd><QuantityValue quantity={run.sample.thickness} expectedUnit="m"/></dd></div></dl></div><div className={s.section}><h3>Условия</h3><dl><div><dt>Режим</dt><dd>{config.dictionaries.gravity_regimes.find(g=>g.value===run.conditions.gravity_regime)?.label??run.conditions.gravity_regime}</dd></div>{conditions.map(([label,value,unit])=><div key={label}><dt>{label}</dt><dd><QuantityValue quantity={value} expectedUnit={unit}/></dd></div>)}<div><dt>Направление потока</dt><dd>{{concurrent:'По направлению',opposed:'Навстречу',quiescent:'Неподвижная среда',other:'Другое',unknown:'Не сообщено'}[run.conditions.flow_configuration]}</dd></div></dl></div><div className={s.section}><h3>Измерения</h3>{run.metrics.length?<dl>{run.metrics.map(metric=><div key={metric.metric_key}><dt>{{burn_duration:'Время горения',visible_extinction_diameter:'Диаметр при видимом погасании',flame_spread_rate:'Скорость распространения',particle_diameter:'Диаметр частиц'}[metric.metric_key]}</dt><dd><QuantityValue quantity={metric.quantity} expectedUnit={metric.metric_key==='burn_duration'?'s':metric.metric_key==='flame_spread_rate'?'m_s':'m'}/></dd></div>)}</dl>:<p className="tiny muted">Измерения не добавлены.</p>}</div>{run.quality_notes.map(note=><p className={s.qualityNote} key={note}>{note}</p>)}<div className={s.evidenceButtons}>{run.evidence_ids.map((id,index)=><button className="textLink" key={id} onClick={()=>onEvidence(id)}>Основание {index+1} <ArrowUpRight size={13}/></button>)}</div></Panel>;
}
