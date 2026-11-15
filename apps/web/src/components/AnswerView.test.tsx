import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { AnswerBlocks } from './AnswerView';
it('renders model text as text and makes evidence IDs the only citation controls', () => {
  render(
    <AnswerBlocks
      answer={{
        answer_blocks: [
          {
            id: 'block_1',
            kind: 'observation',
            text: '<img src=x onerror=alert(1)> https://untrusted.example',
            evidence_ids: ['ev_1'],
            quantities: [],
          },
        ],
        citations: [
          {
            evidence_id: 'ev_1',
            source_id: 'src_1',
            label: 'Check source row',
            locator: { page: 1, section: null, row_key: null, start_s: null, end_s: null },
          },
        ],
      }}
      onEvidence={() => {}}
    />,
  );
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.queryByRole('link')).toBeNull();
  expect(screen.getByText(/<img src=x/)).toBeTruthy();
  expect(screen.getByRole('button', { name: /Check source row/ })).toBeTruthy();
});
