import { expect,it } from 'vitest';
import { pollInterval } from './jobs';
import type { Job } from './types';
const job={state:'running',created_at:'2026-11-14T00:00:00Z',deadline_at:'2026-11-14T00:00:45Z'} as Job;
it('uses the prescribed polling intervals and bounded error backoff',()=>{const start=Date.parse(job.created_at);expect(pollInterval(job,0,start+5000)).toBe(1000);expect(pollInterval(job,0,start+15000)).toBe(2000);expect(pollInterval(job,9,start+15000)).toBe(5000);});
it('stops polling all terminal states and the server deadline',()=>{for(const state of ['succeeded','failed','cancelled','expired'] as const)expect(pollInterval({...job,state},0,Date.parse(job.created_at))).toBe(false);expect(pollInterval(job,0,Date.parse(job.deadline_at))).toBe(false);});
