import { describe, expect, it } from 'vitest';
import {
  formatPeriodForDisplay,
  isQuarterlyPeriodLabel,
} from './reportPresentation';

describe('reportPresentation helpers', () => {
  it('formats fiscal quarter labels for chinese display', () => {
    expect(formatPeriodForDisplay('FY2026 Q3', 'zh')).toBe('2026财年Q3');
    expect(formatPeriodForDisplay('FY2026 Q3', 'en')).toBe('FY2026 Q3');
  });

  it('treats fiscal quarter labels as quarterly periods', () => {
    expect(isQuarterlyPeriodLabel('FY2026 Q3')).toBe(true);
    expect(isQuarterlyPeriodLabel('FY2025')).toBe(false);
  });
});
