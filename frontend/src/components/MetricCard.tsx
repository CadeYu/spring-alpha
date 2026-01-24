// 指标卡片组件 - 显示单个财务指标
import { ArrowUp, ArrowDown, TrendingUp } from 'lucide-react';

interface MetricCardProps {
    title: string;
    value: string;
    change?: number;
    unit?: string;
    icon?: 'revenue' | 'profit' | 'growth' | 'marketcap';
}

export function MetricCard({ title, value, change, unit, icon }: MetricCardProps) {
    const isPositive = change !== undefined && change >= 0;
    const changeColor = isPositive ? 'text-emerald-400' : 'text-red-400';
    const changeBgColor = isPositive ? 'bg-emerald-500/10' : 'bg-red-500/10';

    return (
        <div className="relative group">
            {/* 毛玻璃效果卡片 */}
            <div className="bg-slate-900/50 backdrop-blur-sm border border-slate-800 rounded-lg p-4 hover:border-emerald-500/50 transition-all duration-300 hover:shadow-lg hover:shadow-emerald-500/10">
                {/* 标题 */}
                <div className="text-slate-400 text-sm font-medium mb-2 flex items-center gap-2">
                    {icon === 'revenue' && <span className="text-lg">💰</span>}
                    {icon === 'profit' && <span className="text-lg">💵</span>}
                    {icon === 'growth' && <span className="text-lg">📈</span>}
                    {icon === 'marketcap' && <span className="text-lg">🏢</span>}
                    {title}
                </div>

                {/* 数值 */}
                <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-2xl md:text-3xl font-bold text-white">
                        {value}
                    </span>
                    {unit && (
                        <span className="text-slate-500 text-sm">{unit}</span>
                    )}
                </div>

                {/* 变化百分比 */}
                {change !== undefined && (
                    <div className={`inline-flex items-center gap-1 px-2 py-1 rounded ${changeBgColor}`}>
                        {isPositive ? (
                            <ArrowUp className="w-3 h-3" />
                        ) : (
                            <ArrowDown className="w-3 h-3" />
                        )}
                        <span className={`text-xs font-semibold ${changeColor}`}>
                            {isPositive ? '+' : ''}{change.toFixed(1)}%
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
}
