import { Card, CardContent } from "@/components/ui/card";
import { MetricInsight } from "@/types/AnalysisReport";
import { RevenueChart } from "./RevenueChart";
import { formatFinancialValue } from "@/lib/utils";

interface KeyMetricsProps {
    metrics: MetricInsight[];
    ticker?: string;
}

export function KeyMetrics({ metrics, ticker }: KeyMetricsProps) {
    if (!metrics || metrics.length === 0) return null;

    return (
        <div className="space-y-6">
            <div className="space-y-4">
                <h2 className="text-xl font-semibold text-emerald-300">💰 Key Financial Metrics</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {metrics.map((metric, idx) => (
                        <Card key={idx} className="bg-slate-900 border-slate-800">
                            <CardContent className="p-4">
                                <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                        <h3 className="text-sm font-medium text-slate-400">{metric.metricName}</h3>
                                        <p className="text-2xl font-bold text-emerald-400 mt-1">
                                            {formatFinancialValue(metric.value, metric.metricName)}
                                        </p>
                                    </div>
                                    <div className={`p-2 rounded ${metric.sentiment === 'positive' ? 'bg-green-900/30 text-green-400' :
                                        metric.sentiment === 'negative' ? 'bg-red-900/30 text-red-400' :
                                            'bg-slate-800 text-slate-400'
                                        }`}>
                                        {metric.sentiment === 'positive' ? '📈' : metric.sentiment === 'negative' ? '📉' : '➡️'}
                                    </div>
                                </div>
                                <p className="text-sm text-slate-400 mt-3">{metric.interpretation}</p>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </div>

            {/* Revenue Trend Chart */}
            <RevenueChart ticker={ticker} />
        </div>
    );
}
