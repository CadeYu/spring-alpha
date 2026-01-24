// 风险提示组件 - 显示检测到的风险
import { AlertTriangle, AlertCircle, CheckCircle } from 'lucide-react';

interface RiskAlert {
    level: 'high' | 'medium' | 'low';
    message: string;
}

interface RiskAlertsProps {
    risks: RiskAlert[];
}

export function RiskAlerts({ risks }: RiskAlertsProps) {
    if (risks.length === 0) {
        return (
            <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4">
                <div className="flex items-center gap-2 text-emerald-400">
                    <CheckCircle className="w-5 h-5" />
                    <span className="font-medium">未检测到重大风险</span>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-3">
            <div className="flex items-center gap-2 text-yellow-400 mb-2">
                <AlertTriangle className="w-5 h-5" />
                <span className="font-semibold">检测到 {risks.length} 个风险点</span>
            </div>

            {risks.map((risk, index) => {
                const levelConfig = {
                    high: {
                        icon: AlertTriangle,
                        bg: 'bg-red-500/10',
                        border: 'border-red-500/30',
                        text: 'text-red-400',
                        badge: 'bg-red-500',
                        label: '高风险',
                    },
                    medium: {
                        icon: AlertCircle,
                        bg: 'bg-yellow-500/10',
                        border: 'border-yellow-500/30',
                        text: 'text-yellow-400',
                        badge: 'bg-yellow-500',
                        label: '中等风险',
                    },
                    low: {
                        icon: AlertCircle,
                        bg: 'bg-orange-500/10',
                        border: 'border-orange-500/30',
                        text: 'text-orange-400',
                        badge: 'bg-orange-500',
                        label: '低风险',
                    },
                };

                const config = levelConfig[risk.level];
                const Icon = config.icon;

                return (
                    <div
                        key={index}
                        className={`${config.bg} border ${config.border} rounded-lg p-3`}
                    >
                        <div className="flex items-start gap-3">
                            <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${config.text}`} />
                            <div className="flex-1">
                                <div className="flex items-center gap-2 mb-1">
                                    <span className={`text-xs px-2 py-0.5 rounded ${config.badge} text-white font-medium`}>
                                        {config.label}
                                    </span>
                                </div>
                                <p className={`text-sm ${config.text}`}>{risk.message}</p>
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
