import EarningsAnalystApp from "@/components/app/earnings-analyst-app";

type AppPageProps = {
  searchParams?: Promise<{
    ticker?: string;
  }>;
};

export default async function AppPage({ searchParams }: AppPageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  return <EarningsAnalystApp initialTicker={resolvedSearchParams?.ticker ?? ""} />;
}
