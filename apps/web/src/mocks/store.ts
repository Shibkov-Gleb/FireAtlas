import { openDB } from 'idb';
import type { AnalysisResult, Job, Report, Scenario, Schema, Workspace } from '../api/types';

export type StoredJob = { job: Job; input: Schema['AnalysisRequest'] | Schema['ReportRequest']; snapshot: Scenario; created: number; mock: string; };
export type DemoState = { workspace: Workspace | null; jobs: Record<string, StoredJob>; answers: Record<string, AnalysisResult>; reports: Record<string, Report>; idempotency: Record<string, { fingerprint: string; jobId: string; created: number }>; };
const database = openDB('fireatlas-demo-v1', 1, { upgrade(db) { db.createObjectStore('state'); } });
export function initialState(): DemoState { return { workspace: null, jobs: {}, answers: {}, reports: {}, idempotency: {} }; }
// A read/write transaction serializes revisions across tabs, just as the real server must.
export async function withState<T>(fn: (state: DemoState) => T): Promise<T> {
  const db = await database;
  const transaction = db.transaction('state', 'readwrite');
  const state: DemoState = (await transaction.store.get('snapshot')) ?? initialState();
  const result = fn(state);
  await transaction.store.put(state, 'snapshot');
  await transaction.done;
  return result;
}
