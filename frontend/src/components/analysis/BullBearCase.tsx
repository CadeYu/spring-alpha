import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface BullBearCaseProps {
    bullCase: string;
    bearCase: string;
}

export function BullBearCase({ bullCase, bearCase }: BullBearCaseProps) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card className="bg-green-900/10 border-green-800">
                <CardHeader className="border-b border-green-800">
                    <CardTitle className="text-green-400">🐂 Bull Case</CardTitle>
                </CardHeader>
                <CardContent className="p-6">
                    <p className="text-slate-300">{bullCase}</p>
                </CardContent>
            </Card>

            <Card className="bg-red-900/10 border-red-800">
                <CardHeader className="border-b border-red-800">
                    <CardTitle className="text-red-400">🐻 Bear Case</CardTitle>
                </CardHeader>
                <CardContent className="p-6">
                    <p className="text-slate-300">{bearCase}</p>
                </CardContent>
            </Card>
        </div>
    );
}
