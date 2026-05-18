"use client";

import { signIn } from "next-auth/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { KeyRound, Sparkles } from "lucide-react";

export type TrialGateStatus = "anonymous_ready" | "authenticated_ready" | "trial_exhausted";

type TrialGateProps = {
  status: TrialGateStatus;
};

export function TrialGate({ status }: TrialGateProps) {
  if (status !== "trial_exhausted") {
    return null;
  }

  return (
    <Card className="border-amber-500/20 bg-amber-500/5 shadow-none">
      <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Badge className="bg-amber-500/10 text-amber-300 hover:bg-amber-500/10">
              Trial exhausted
            </Badge>
            <span className="inline-flex items-center gap-1 text-xs uppercase tracking-widest text-slate-500">
              <Sparkles className="h-3.5 w-3.5" />
              Free trial reached
            </span>
          </div>
          <p className="text-sm font-medium text-slate-100">
            You have used your free analysis.
          </p>
          <p className="max-w-2xl text-sm text-slate-400">
            Sign in with Google and continue with your own key to keep analyzing tickers.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          className="border-amber-500/30 bg-transparent"
          onClick={() => void signIn("google")}
        >
          <KeyRound className="h-4 w-4" />
          Sign in with Google
        </Button>
      </CardContent>
    </Card>
  );
}
