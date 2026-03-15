import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ExecutiveSummary } from './ExecutiveSummary';

describe('ExecutiveSummary', () => {
  it('renders four question sections and falls back to business signals when thesis fields are absent', () => {
    render(
      <ExecutiveSummary
        lang="zh"
        thesis={{
          verdict: 'mixed',
          headline: '云与AI仍是核心主线',
          summary: '公司本季的业务主线仍由企业云需求与AI商业化推进驱动。',
        }}
        businessSignals={{
          segmentPerformance: [
            {
              title: 'Azure / cloud momentum',
              summary: 'Azure revenue grew as enterprise AI demand remained strong.',
            },
          ],
          managementFocus: [
            {
              title: 'Execution discipline',
              summary: 'Management continues to prioritize efficiency while expanding AI capacity.',
            },
          ],
          strategicMoves: [
            {
              title: 'Copilot commercialization',
              summary: 'Copilot adoption expanded across commercial customers.',
            },
          ],
          riskSignals: [
            {
              title: 'Infrastructure buildout',
              summary: 'Watch whether AI infrastructure spend continues to outpace monetization.',
            },
          ],
        }}
      />,
    );

    expect(screen.getByText('本季发生了什么')).toBeInTheDocument();
    expect(screen.getByText('核心驱动因素')).toBeInTheDocument();
    expect(screen.getByText('公司在押注什么')).toBeInTheDocument();
    expect(screen.getByText('后续跟踪什么')).toBeInTheDocument();
    expect(screen.getAllByText(/Azure revenue grew as enterprise AI demand remained strong/).length).toBeGreaterThan(0);
    expect(screen.getByText('Management continues to prioritize efficiency while expanding AI capacity.')).toBeInTheDocument();
    expect(screen.getByText('Copilot adoption expanded across commercial customers.')).toBeInTheDocument();
    expect(screen.getByText('Infrastructure buildout: Watch whether AI infrastructure spend continues to outpace monetization.'))
      .toBeInTheDocument();
  });

  it('prefers structured four-question thesis fields when they exist', () => {
    render(
      <ExecutiveSummary
        lang="en"
        thesis={{
          verdict: 'positive',
          headline: 'Platform engagement stayed healthy',
          summary: 'Advertising demand held up as recommendation quality improved.',
          whatChanged: ['Recommendation quality continued to lift engagement.'],
          drivers: [
            {
              label: 'Ad platform',
              detail: 'Management highlighted stronger ad conversion across recommendation surfaces.',
            },
          ],
          strategicBets: [
            {
              label: 'Meta AI',
              detail: 'The company is still investing behind Meta AI and business messaging monetization.',
            },
          ],
          watchItems: ['Watch whether AI infrastructure spend continues to outpace monetization.'],
        }}
      />,
    );

    expect(screen.getByText('What Changed')).toBeInTheDocument();
    expect(screen.getByText('What Drove It')).toBeInTheDocument();
    expect(screen.getByText('What Is The Bet')).toBeInTheDocument();
    expect(screen.getByText('What To Watch')).toBeInTheDocument();
    expect(screen.getByText('Recommendation quality continued to lift engagement.')).toBeInTheDocument();
    expect(screen.getByText('Management highlighted stronger ad conversion across recommendation surfaces.'))
      .toBeInTheDocument();
    expect(screen.getByText('The company is still investing behind Meta AI and business messaging monetization.'))
      .toBeInTheDocument();
    expect(screen.getByText('Watch whether AI infrastructure spend continues to outpace monetization.'))
      .toBeInTheDocument();
  });
});
