import { expect,it } from 'vitest';
import { quantity } from '../mocks/fixtures';
import { formatQuantity } from './format';
it('distinguishes zero, null, not applicable and unusable values',()=>{expect(formatQuantity(quantity(0,'m_s',['ev_0'],'0','m/s'))).toBe('0 см/с');expect(formatQuantity(quantity(null,'Pa'))).toBe('Не сообщено в источнике');expect(formatQuantity({...quantity(null,'m'),status:'not_applicable'})).toBe('Неприменимо');expect(formatQuantity({...quantity(null,'m'),status:'unusable'})).toBe('Значение или единица непригодны');});
it('converts canonical lengths without adding significant digits',()=>{expect(formatQuantity(quantity(.00192,'m',['ev_1'],'1.92','mm'),'m')).toBe('1,92 мм');expect(formatQuantity(quantity(6.34,'s',['ev_1'],'6.34','s'),'s')).toBe('6,34 с');expect(formatQuantity(quantity(.21,'fraction',['ev_1'],'0.21','fraction'))).toBe('21 %');});
it('does not present mismatched units as a valid parameter',()=>{expect(formatQuantity(quantity(1,'s',['ev_1']),'m')).toBe('Единица несовместима с параметром');});
