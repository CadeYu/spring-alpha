import { describe, expect, it } from 'vitest';
import {
  formatPeriodForDisplay,
  getSourceMessage,
  getSourceStatusLabel,
  isQuarterlyPeriodLabel,
  mergeSourceContexts,
  normalizeSourceStatus,
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

  it('normalizes legacy grounded-no-citation banners into limited source status', () => {
    const sourceContext = {
      status: 'GROUNDED' as const,
      message: 'Grounded SEC evidence was retrieved, but no high-confidence verbatim citations survived validation for this run.',
    };

    expect(normalizeSourceStatus(sourceContext)).toBe('LIMITED');
    expect(getSourceStatusLabel(sourceContext, 'en')).toBe('grounded evidence, citation display limited');
    expect(getSourceMessage(sourceContext, 'zh')).toContain('高置信逐字引用');
  });

  it('preserves limited source status when a later chunk falls back to grounded metadata', () => {
    const merged = mergeSourceContexts(
      {
        status: 'LIMITED',
        message: 'SEC source evidence was retrieved, but this run did not retain a display-ready high-confidence verbatim quote.',
      },
      {
        status: 'GROUNDED',
        message: 'Grounded in SEC text evidence.',
      },
    );

    expect(merged?.status).toBe('LIMITED');
    expect(getSourceStatusLabel(merged, 'zh')).toBe('有来源依据，引用展示受限');
  });

  it('localizes known degraded english backend messages for chinese display', () => {
    const sourceContext = {
      status: 'DEGRADED' as const,
      message: 'SEC filing was available, but semantic grounding was not ready yet. This run is operating without verifiable citations.',
    };

    expect(getSourceMessage(sourceContext, 'zh')).toContain('语义 grounding 尚未就绪');
    expect(getSourceMessage(sourceContext, 'zh')).not.toContain('SEC filing was available');
  });
});
