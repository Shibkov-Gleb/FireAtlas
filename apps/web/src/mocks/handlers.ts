import { delay, http, HttpResponse } from 'msw';
import type { AnalysisResult, Job, Schema } from '../api/types';
import { isTerminal } from '../api/types';
import { applicability, claims, config, evidence, extraInvestigation, investigations, orbitalScenario, REVISION, runs, sources } from './fixtures';
import { comparisonFixture, fingerprint, measurementFixture, searchFixture } from './logic';
import { withState, type DemoState, type StoredJob } from './store';

const now = () => new Date().toISOString();
const meta = () => ({request_id:`req_${crypto.randomUUID()}`,contract_version:'1.0.0',data_revision:REVISION,warnings:[]});
const success = <T,>(data:T,status=200,headers:Record<string,string>={}) => HttpResponse.json({data,meta:meta()},{status,headers});
export const failure = (status:number,code:string,message:string,retryable=false,details:Schema['ErrorDetail'][]=[]) => HttpResponse.json({error:{code,message,retryable,details},meta:meta()},{status,headers:status===429?{'Retry-After':'2'}:{}});
const mockMode = (request:Request) => request.headers.get('X-FireAtlas-Mock')??'';
const wrongRevision = (request:Request) => {const revision=new URL(request.url).searchParams.get('data_revision');return revision && revision!==REVISION;};
function revisionError(){return failure(410,'DATA_REVISION_GONE','Эта ревизия корпуса больше недоступна. Создайте новое пространство.');}
function sessionError(){return failure(401,'SESSION_REQUIRED','Гостевое пространство недоступно. Создайте новое, чтобы продолжить.');}
function conflict(revision:number){return failure(409,'WORKSPACE_CONFLICT','Контекст изменился в другой вкладке. Обновите его перед повтором.',false,[{field:'workspace_revision',reason:'stale_revision',current_revision:revision}]);}
function makeAnswer(record:StoredJob): AnalysisResult {
  const input=record.input as Schema['AnalysisRequest'];
  const status:AnalysisResult['status']=record.mock==='insufficient_evidence'?'insufficient_evidence':record.mock==='conflicting_evidence'?'conflicting_evidence':'answered';
  return {id:record.job.result_id!,data_revision:REVISION,workspace_revision:input.workspace_revision,scenario_snapshot:record.snapshot,question:input.question,status,answer_blocks:[
    {id:'block_summary',kind:'summary',text:status==='insufficient_evidence'?'Недостаточно данных для ответа в заданных условиях.':status==='conflicting_evidence'?'В демонстрационном примере основания расходятся; сравните условия.':'Демонстрационный ответ: изучайте поток воздуха вместе с материалом, геометрией и атмосферой.',evidence_ids:['ev_demo_bass'],quantities:[]},
    {id:'block_observation',kind:'observation',text:'В контрольной записи FLEX 30CAL03 время горения составляет 6,34 с.',evidence_ids:['ev_psi69_30cal03'],quantities:[{name:'burn_duration',quantity:runs.find(r=>r.source_test_id==='30CAL03')!.metrics[0]!.quantity,evidence_ids:['ev_psi69_30cal03']}]},
    {id:'block_synthesis',kind:'synthesis',text:'FLEX изучает капли жидкости, BASS-II — твёрдые образцы. Между этими опытами нельзя автоматически переносить численные результаты.',evidence_ids:['ev_demo_bass','ev_psi69_30cal03'],quantities:[]},
    {id:'block_limitation',kind:'limitation',text:'Это заранее подготовленный UI-пример, а не новый анализ модели. Для научного вывода необходим проверенный корпус доказательств.',evidence_ids:[],quantities:[]},
  ],applicability:applicability(record.snapshot),citations:evidence.filter(e=>['ev_demo_bass','ev_psi69_30cal03'].includes(e.id)).map(e=>({evidence_id:e.id,source_id:e.source_id,label:e.source_id==='src_psi69'?'FLEX · 30CAL03':'BASS-II · метаданные',locator:e.locator})),limitations:['Нет оценки безопасности аппарата или вероятности пожара.',...(record.snapshot.gravity_regime==='partial'?['Нет прямых измерений частичной гравитации.']:[])],follow_up_questions:['Какие условия образца и атмосферы известны?'],retrieval_mode:'lexical',reasoning_revision:'demo-prepared-example-v1',validation_summary:{schema_valid:true,references_valid:true,quantities_valid:true,scope_valid:true},created_at:now()};
}
function advanceJob(state:DemoState,record:StoredJob){
  const job=record.job;
  if(isTerminal(job.state))return;
  const elapsed=Date.now()-record.created;
  if(Date.now()>=Date.parse(job.deadline_at)){job.state='expired';job.stage=null;job.error={code:'JOB_TIMEOUT',message:'Истёк срок подготовки результата.',details:[],retryable:true};}
  else if(elapsed<500){job.state='queued';job.stage=null;}
  else if(elapsed<3500){job.state='running';job.stage=job.type==='report'?'exporting':elapsed<1300?'retrieving':elapsed<2500?'reasoning':'validating';}
  else if(record.mock==='provider_error'||record.mock==='ai_unavailable'){job.state='failed';job.stage=null;job.error={code:record.mock==='provider_error'?'MODEL_PROVIDER_ERROR':'AI_UNAVAILABLE',message:'Внешняя модель недоступна. Найденные источники можно открыть.',retryable:true,details:[]};job.fallback_evidence_ids=['ev_demo_bass','ev_psi69_30cal03'];}
  else {job.state='succeeded';job.stage=null;job.result_id=`${job.type==='analysis'?'ans':'rpt'}_${job.id.slice(4)}`;if(job.type==='analysis')state.answers[job.result_id]=makeAnswer(record);else state.reports[job.result_id]={id:job.result_id,state:'ready',title:(record.input as Schema['ReportRequest']).title,source_workspace_revision:record.input.workspace_revision,data_revision:REVISION,created_at:now(),expires_at:new Date(Date.now()+86400000).toISOString(),download_path:`/api/v1/reports/${job.result_id}/download`,sha256:null,error:null};}
  job.updated_at=now();
}
async function createJob(request:Request,type:Job['type']){
  const input=await request.json() as Schema['AnalysisRequest']|Schema['ReportRequest'];
  const key=request.headers.get('Idempotency-Key');
  if(!key||!/^[a-f\d-]{36}$/i.test(key))return failure(422,'VALIDATION_ERROR','Требуется UUID Idempotency-Key.');
  return withState(state=>{
    const workspace=state.workspace;if(!workspace)return sessionError();
    const scope=`${workspace.id}:${type}:${key}`;const saved=state.idempotency[scope];
    if(saved&&Date.now()-saved.created<86400000){if(saved.fingerprint!==fingerprint(input))return failure(409,'IDEMPOTENCY_CONFLICT','Этот ключ уже использован с другим запросом.');return success(state.jobs[saved.jobId]!.job,202);}
    if(input.workspace_revision!==workspace.revision)return conflict(workspace.revision);
    if(type==='analysis'&&((input as Schema['AnalysisRequest']).question.trim().length<3||(input as Schema['AnalysisRequest']).question.length>2000))return failure(422,'VALIDATION_ERROR','Вопрос должен содержать от 3 до 2000 символов.');
    if(type==='report'){const report=input as Schema['ReportRequest'];if(report.title.trim().length<3||report.title.length>120||!report.answer_ids.length&&!report.investigation_ids.length)return failure(422,'VALIDATION_ERROR','Укажите название и хотя бы один материал.');if(report.answer_ids.some(id=>!state.answers[id]))return failure(403,'ACCESS_DENIED','Ответ недоступен в текущем пространстве.');}
    if(type==='analysis'&&(input as Schema['AnalysisRequest']).data_revision!==REVISION)return revisionError();
    const mock=mockMode(request);const id=`job_${crypto.randomUUID().replaceAll('-','')}`;const timestamp=now();
    const job:Job={id,type,state:'queued',stage:null,created_at:timestamp,updated_at:timestamp,deadline_at:new Date(Date.now()+(mock==='timeout'?2500:type==='analysis'?45000:30000)).toISOString(),result_kind:type==='analysis'?'answer':'report',result_id:null,error:null,input_context:{workspace_revision:workspace.revision,data_revision:REVISION,scenario_id:workspace.scenario.scenario_id},fallback_evidence_ids:[]};
    state.jobs[id]={job,input,snapshot:structuredClone(workspace.scenario),created:Date.now(),mock};state.idempotency[scope]={jobId:id,fingerprint:fingerprint(input),created:Date.now()};return success(job,202);
  });
}
export const handlers=[
  http.get('/api/v1/config',({request})=>mockMode(request)==='data_not_ready'?failure(503,'DATA_NOT_READY','Корпус ещё не подготовлен.',true):success(config)),
  http.post('/api/v1/workspaces',()=>withState(state=>{const exists=!!state.workspace;if(!state.workspace){const timestamp=now();state.workspace={id:`ws_${crypto.randomUUID().replaceAll('-','')}`,revision:1,scenario:structuredClone(orbitalScenario),selected_investigation_ids:[],saved_investigation_ids:[],saved_answer_ids:[],data_revision:REVISION,created_at:timestamp,updated_at:timestamp,expires_at:new Date(Date.now()+7*86400000).toISOString()};}return success(state.workspace,exists?200:201,{ETag:`"${state.workspace.revision}"`});})),
  http.get('/api/v1/workspaces/current',({request})=>withState(state=>!state.workspace||mockMode(request)==='session_expired'?sessionError():success(state.workspace,200,{ETag:`"${state.workspace.revision}"` }))),
  http.patch('/api/v1/workspaces/current',async({request})=>{const patch=await request.json() as Schema['WorkspacePatch'];return withState(state=>{const workspace=state.workspace;if(!workspace)return sessionError();if(request.headers.get('If-Match')!==`"${workspace.revision}"`)return conflict(workspace.revision);if(patch.selected_investigation_ids&&new Set(patch.selected_investigation_ids).size>3)return failure(422,'VALIDATION_ERROR','Можно сравнить не более трёх исследований.');if(patch.saved_answer_ids?.some(id=>!state.answers[id]))return failure(403,'ACCESS_DENIED','Ответ недоступен.');Object.assign(workspace,patch);for(const key of ['selected_investigation_ids','saved_investigation_ids','saved_answer_ids'] as const)workspace[key]=[...new Set(workspace[key])];workspace.revision++;workspace.updated_at=now();return success(workspace,200,{ETag:`"${workspace.revision}"`});});}),
  http.post('/api/v1/search',async({request})=>{const body=await request.json() as Schema['SearchRequest'];if(body.data_revision!==REVISION)return revisionError();if(mockMode(request)==='rate_limited')return failure(429,'RATE_LIMITED','Слишком много запросов. Повторите через несколько секунд.',true);await delay(mockMode(request)==='slow_search'?1000:120);try{return success(searchFixture(body,mockMode(request)==='comparison_limit'));}catch{return failure(422,'INVALID_CURSOR','Параметры выдачи изменились. Начните поиск заново.');}}),
  http.get('/api/v1/investigations/:id',({params,request})=>{if(wrongRevision(request))return revisionError();const investigation=[...investigations,extraInvestigation].find(i=>i.id===params.id);if(!investigation)return failure(404,'NOT_FOUND','Исследование не найдено.');const records=runs.filter(r=>r.investigation_id===investigation.id);return success({investigation,claims:claims.filter(c=>c.investigation_ids.includes(investigation.id)),sources:sources.filter(s=>investigation.source_ids.includes(s.id)),run_summary:{total:records.length,verified_count:records.length,excluded_count:0}});}),
  http.get('/api/v1/investigations/:id/runs',({params,request})=>{if(wrongRevision(request))return revisionError();if(!investigations.some(i=>i.id===params.id))return failure(404,'NOT_FOUND','Исследование не найдено.');const records=runs.filter(r=>r.investigation_id===params.id);return success({items:records,next_cursor:null,total:records.length});}),
  http.get('/api/v1/runs/:id',({params,request})=>{if(wrongRevision(request))return revisionError();const run=runs.find(r=>r.id===params.id);return run?success(run):failure(404,'NOT_FOUND','Опыт не найден.');}),
  http.get('/api/v1/evidence/:id',({params,request})=>{if(wrongRevision(request))return revisionError();const record=evidence.find(e=>e.id===params.id);return record?success({evidence:record,source:sources.find(s=>s.id===record.source_id)!}):failure(404,'NOT_FOUND','Доказательство не найдено.');}),
  http.get('/api/v1/sources/:id',({params,request})=>{if(wrongRevision(request))return revisionError();const source=sources.find(s=>s.id===params.id);return source?success(source):failure(404,'NOT_FOUND','Источник не найден.');}),
  http.post('/api/v1/measurements/query',async({request})=>{const body=await request.json() as Schema['MeasurementRequest'];if(body.data_revision!==REVISION)return revisionError();return success(measurementFixture(body));}),
  http.post('/api/v1/comparisons',async({request})=>{const body=await request.json() as Schema['ComparisonRequest'];if(body.data_revision!==REVISION)return revisionError();if(new Set(body.investigation_ids).size<2||new Set(body.investigation_ids).size>3)return failure(422,'VALIDATION_ERROR','Выберите два или три разных исследования.');const selected=[...investigations,extraInvestigation].filter(i=>body.investigation_ids.includes(i.id));const scenario=body.scenario??orbitalScenario;return success({...comparisonFixture(selected,scenario),applicability:applicability(scenario)});}),
  http.post('/api/v1/applicability',async({request})=>{const body=await request.json() as Schema['ApplicabilityRequest'];return body.data_revision===REVISION?success(applicability(body.scenario)):revisionError();}),
  http.post('/api/v1/analyses',({request})=>createJob(request,'analysis')),
  http.post('/api/v1/reports',({request})=>createJob(request,'report')),
  http.get('/api/v1/jobs/:id',({params})=>withState(state=>{const record=state.jobs[String(params.id)];if(!record||!state.workspace)return failure(403,'ACCESS_DENIED','Задача недоступна в этом пространстве.');advanceJob(state,record);return success(record.job);})),
  http.delete('/api/v1/jobs/:id',({params})=>withState(state=>{const record=state.jobs[String(params.id)];if(!record)return failure(404,'NOT_FOUND','Задача не найдена.');advanceJob(state,record);if(isTerminal(record.job.state))return failure(409,'JOB_ALREADY_FINISHED','Задача уже завершена.');record.job.state='cancelled';record.job.stage=null;record.job.updated_at=now();return new HttpResponse(null,{status:204});})),
  http.get('/api/v1/answers/:id',({params})=>withState(state=>state.workspace&&state.answers[String(params.id)]?success(state.answers[String(params.id)]):failure(403,'ACCESS_DENIED','Ответ недоступен в этом пространстве.'))),
  http.get('/api/v1/reports/:id',({params,request})=>withState(state=>{const report=state.reports[String(params.id)];if(!report||!state.workspace)return failure(403,'ACCESS_DENIED','Отчёт недоступен.');if(mockMode(request)==='report_expired'||Date.now()>Date.parse(report.expires_at)){report.state='expired';report.download_path=null;return failure(410,'RESOURCE_EXPIRED','Срок хранения отчёта истёк. Подготовьте новый.');}return success(report);})),
  http.get('/api/v1/reports/:id/download',async({params,request})=>{const allowed=await withState(state=>!!state.workspace&&!!state.reports[String(params.id)]&&Date.now()<Date.parse(state.reports[String(params.id)]!.expires_at));if(!allowed||mockMode(request)==='report_expired')return failure(410,'RESOURCE_EXPIRED','Срок скачивания отчёта истёк.');const response=await fetch('/demo-report.pdf');if(!response.ok)return failure(503,'DATA_NOT_READY','PDF-пример ещё не подготовлен.');return new HttpResponse(await response.arrayBuffer(),{headers:{'Content-Type':'application/pdf','Content-Disposition':'attachment; filename="fire-atlas-demo.pdf"'}});}),
];
