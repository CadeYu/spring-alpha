import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RiskFactor } from "@/types/AnalysisReport";

interface RiskFactorsProps {
    risks: RiskFactor[];
}

export function RiskFactors({ risks }: RiskFactorsProps) {
    if (!risks || risks.length === 0) return null;

    return (
        <Card className="bg-slate-900 border-slate-800">
            <CardHeader className="border-b border-slate-800">
                <CardTitle className="text-red-400">⚠️ Risk Factors</CardTitle>
            </CardHeader>
            <CardContent className="p-6 space-y-4">
                {risks.map((risk, idx) => (
                    <div key={idx} className="border-l-4 border-red-500 pl-4">
                        <h4 className="font-semibold text-white">{risk.category}</h4>
                        <p className="text-sm text-slate-400 mt-1">{risk.description}</p>
                        <span className={`text-xs mt-2 inline-block px-2 py-1 rounded ${risk.severity === 'high' ? 'bg-red-900/30 text-red-400' :
                                risk.severity === 'medium' ? 'bg-yellow-900/30 text-yellow-400' :
                                    'bg-slate-800 text-slate-400'
                            }`}>
                            Severity: {risk.severity}
                        </span>
                    </div>
                ))}
            </CardContent>
        </Card>
    );
}
