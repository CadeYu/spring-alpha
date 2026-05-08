export const RESEARCH_TASK_IDS = [
  "latest_earnings_readout",
  "business_driver_deep_dive",
  "cash_flow_capital_allocation",
] as const;

export type ResearchTaskId = (typeof RESEARCH_TASK_IDS)[number];

export const DEFAULT_RESEARCH_TASK_ID: ResearchTaskId =
  "latest_earnings_readout";

export function isResearchTaskId(value: string): value is ResearchTaskId {
  return RESEARCH_TASK_IDS.includes(value as ResearchTaskId);
}
