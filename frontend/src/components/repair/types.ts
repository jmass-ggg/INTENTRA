/**
 * Type definitions for repair components
 */

export type RepairStrategy =
  | 'YES_NO'
  | 'SHOW_CHOICES'
  | 'SIMPLIFY'
  | 'TIME_SELECTION'
  | 'BODY_LOCATION'
  | 'KEYWORD_ONLY'
  | 'REPHRASE'
  | 'EXPAND';

export interface RepairOption {
  label: string;
  value: string;
}

export interface RepairPlan {
  strategy: RepairStrategy;
  question?: string;
  options: RepairOption[];
  rebuilt_expression?: string;
}
