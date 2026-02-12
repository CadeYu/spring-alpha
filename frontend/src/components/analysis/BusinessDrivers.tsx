import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BusinessDriver } from "@/types/AnalysisReport";

interface BusinessDriversProps {
    drivers: BusinessDriver[];
    lang?: string;
}

export function BusinessDrivers({ drivers, lang = 'en' }: BusinessDriversProps) {
    if (!drivers || drivers.length === 0) return null;

    const isZh = lang === 'zh';

    return (
        <Card className="bg-slate-900 border-slate-800">
            <CardHeader className="border-b border-slate-800">
                <CardTitle className="text-emerald-400">🚀 {isZh ? '业务驱动因素' : 'Business Drivers'}</CardTitle>
            </CardHeader>
            <CardContent className="p-6 space-y-4">
                {drivers.map((driver, idx) => (
                    <div key={idx} className="border-l-4 border-emerald-500 pl-4">
                        <h4 className="font-semibold text-white">{driver.title}</h4>
                        <p className="text-sm text-slate-400 mt-1">{driver.description}</p>
                        <span className={`text-xs mt-2 inline-block px-2 py-1 rounded ${driver.impact === 'high' ? 'bg-emerald-900/30 text-emerald-400' :
                            driver.impact === 'medium' ? 'bg-yellow-900/30 text-yellow-400' :
                                'bg-slate-800 text-slate-400'
                            }`}>
                            {isZh ? '影响: ' : 'Impact: '}{isZh ? (driver.impact === 'high' ? '高' : driver.impact === 'medium' ? '中' : driver.impact === 'low' ? '低' : driver.impact) : driver.impact}
                        </span>
                    </div>
                ))}
            </CardContent>
        </Card>
    );
}
