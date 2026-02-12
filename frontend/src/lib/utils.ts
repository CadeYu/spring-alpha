import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatFinancialValue(value: string | number | null | undefined, name: string, currency: string = 'USD'): string {
  // Handle null/undefined values gracefully
  if (value === null || value === undefined || value === '') {
    return 'N/A';
  }

  const num = typeof value === 'string' ? parseFloat(value) : value;

  // Return original if not a number
  if (isNaN(num)) return String(value);

  const lowerName = name.toLowerCase();

  // Percentage Formatting
  // Check common financial terms for percentages
  const isPercentage =
    lowerName.includes('margin') ||
    lowerName.includes('rate') ||
    lowerName.includes('growth') ||
    lowerName.includes('change') ||
    lowerName.includes('return') ||
    lowerName.includes('roe') ||
    lowerName.includes('roa') ||
    lowerName.includes('yield');

  if (isPercentage) {
    // If value is like 0.4491, it's 44.91%
    // If value is like 44.91, assume it's already percentage (heuristic)
    // Most financial raw data (XBRL) uses decimals for ratios (0.4491)
    const percentValue = Math.abs(num) <= 1.5 ? num * 100 : num;
    return `${percentValue.toFixed(2)}%`;
  }

  // Currency Symbol Logic
  let symbol = '$';
  if (currency === 'JPY') symbol = '¥';
  else if (currency === 'EUR') symbol = '€';
  else if (currency === 'CNY') symbol = '¥';
  else if (currency === 'GBP') symbol = '£';
  else if (currency !== 'USD' && currency.length === 3) symbol = currency + ' '; // Fallback for other currencies

  // Currency/Large Number Formatting
  const isCurrency =
    lowerName.includes('revenue') ||
    lowerName.includes('income') ||
    lowerName.includes('profit') ||
    lowerName.includes('cash') ||
    lowerName.includes('assets') ||
    lowerName.includes('liabilities') ||
    lowerName.includes('equity') ||
    lowerName.includes('debt') ||
    lowerName.includes('sales');

  if (isCurrency || Math.abs(num) > 1_000_000) {
    if (Math.abs(num) >= 1_000_000_000_000) { // Support Trillions for JPY
      return `${symbol}${(num / 1_000_000_000_000).toFixed(2)}T`;
    }
    if (Math.abs(num) >= 1_000_000_000) {
      return `${symbol}${(num / 1_000_000_000).toFixed(2)}B`;
    }
    if (Math.abs(num) >= 1_000_000) {
      return `${symbol}${(num / 1_000_000).toFixed(2)}M`;
    }
    return `${symbol}${num.toLocaleString()}`;
  }

  return num.toLocaleString();
}
