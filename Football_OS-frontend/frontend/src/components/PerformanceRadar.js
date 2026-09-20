import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from "recharts";

export default function PerformanceRadar({ data, color = "var(--cyan)", testId = "performance-radar" }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="radar-wrap" data-testid={testId}>
      <ResponsiveContainer width="100%" height={280}>
        <RadarChart data={data} margin={{ top: 12, right: 22, left: 22, bottom: 12 }}>
          <PolarGrid stroke="#233040" />
          <PolarAngleAxis dataKey="label" tick={{ fill: "var(--muted)", fontSize: 11 }} />
          <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
          <Radar name="Percentile" dataKey="value" stroke={color} fill={color} fillOpacity={0.22} strokeWidth={1.4} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
