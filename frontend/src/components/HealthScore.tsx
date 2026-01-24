// 健康度评分组件 - 显示财务健康度
interface HealthScoreProps {
    score: number;  // 0-100
    label?: string;
}

export function HealthScore({ score, label }: HealthScoreProps) {
    // 根据分数确定颜色和等级
    const getScoreColor = (score: number) => {
        if (score >= 80) return { color: 'emerald', label: '优秀' };
        if (score >= 60) return { color: 'yellow', label: '良好' };
        if (score >= 40) return { color: 'orange', label: '一般' };
        return { color: 'red', label: '较差' };
    };

    const { color, label: autoLabel } = getScoreColor(score);
    const displayLabel = label || autoLabel;

    const colorClasses = {
        emerald: 'bg-emerald-500',
        yellow: 'bg-yellow-500',
        orange: 'bg-orange-500',
        red: 'bg-red-500',
    };

    const textColorClasses = {
        emerald: 'text-emerald-400',
        yellow: 'text-yellow-400',
        orange: 'text-orange-400',
        red: 'text-red-400',
    };

    return (
        <div className="bg-slate-900/50 backdrop-blur-sm border border-slate-800 rounded-lg p-6">
            {/* 标题 */}
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-slate-300">财务健康度</h3>
                <span className={`text-2xl font-bold ${textColorClasses[color as keyof typeof textColorClasses]}`}>
                    {displayLabel}
                </span>
            </div>

            {/* 进度条 */}
            <div className="relative">
                {/* 背景轨道 */}
                <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                    {/* 进度填充 - 带动画 */}
                    <div
                        className={`h-full ${colorClasses[color as keyof typeof colorClasses]} rounded-full transition-all duration-1000 ease-out`}
                        style={{ width: `${score}%` }}
                    />
                </div>

                {/* 分数显示 */}
                <div className="flex justify-between mt-2 text-sm">
                    <span className="text-slate-500">0</span>
                    <span className={`font-semibold ${textColorClasses[color as keyof typeof textColorClasses]}`}>
                        {score}/100
                    </span>
                    <span className="text-slate-500">100</span>
                </div>
            </div>
        </div>
    );
}
