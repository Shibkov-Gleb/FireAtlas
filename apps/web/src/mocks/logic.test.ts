import { describe, expect, it } from 'vitest';
import { emptyFilters } from '../api/types';
import { flexRuns, REVISION } from './fixtures';
import { defaultSearch, measurementFixture, searchFixture } from './logic';

describe('scientific fixture behavior',()=>{
  it('retains all five FLEX coordinates and the disruption outcome',()=>{const result=measurementFixture({investigation_id:'inv_psi69',data_revision:REVISION,run_ids:[],x_metric:'sample.initial_diameter',y_metric:'metrics.burn_duration',filters:emptyFilters(),cursor:null,limit:200});expect(result.points.map(p=>[p.x*1000,p.y])).toEqual([[1.69,4.3],[1.86,5],[1.61,3.2],[2.06,7.64],[1.92,6.34]]);expect(result.points[0]?.outcome).toBe('disruption');expect(flexRuns[0]?.conditions.pressure.value).not.toBe(flexRuns[1]?.conditions.pressure.value);});
  it('keeps hard ranges even when related work is requested',()=>{const query=defaultSearch(REVISION);query.include_related=true;query.filters.oxygen_range={min:.9,max:1,unit:'fraction'};expect(searchFixture(query).items).toHaveLength(0);});
  it('does not substitute a coordinate for missing data',()=>{const result=measurementFixture({investigation_id:'inv_psi25',data_revision:REVISION,run_ids:[],x_metric:'sample.initial_diameter',y_metric:'metrics.burn_duration',filters:emptyFilters(),cursor:null,limit:200});expect(result.points).toHaveLength(0);expect(result.excluded_count).toBe(1);});
  it('rejects cursors from a different query',()=>{const query={...defaultSearch(REVISION),limit:1};const first=searchFixture(query);expect(()=>searchFixture({...query,cursor:first.next_cursor,sort:'title'})).toThrow('INVALID_CURSOR');});
});
