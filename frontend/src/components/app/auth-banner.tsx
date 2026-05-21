"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { KeyRound, LogIn, LogOut, UserCircle2 } from "lucide-react";

type AuthBannerProps = {
  lang?: "zh" | "en";
};

export function AuthBanner({ lang = "en" }: AuthBannerProps) {
  const isZh = lang === "zh";
  const { data: session, status } = useSession();

  if (status === "loading") {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-400">
        {isZh ? "正在检查 Google 登录状态..." : "Checking Google session..."}
      </div>
    );
  }

  if (status === "authenticated") {
    const userLabel = session?.user?.email ?? session?.user?.name ?? "Google user";

    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-500/20 bg-slate-950/80 px-4 py-3 text-sm text-slate-200">
        <div className="flex min-w-0 items-center gap-3">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
            <UserCircle2 className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="font-medium text-emerald-100">{userLabel}</p>
            <p className="text-xs text-slate-400">
              {isZh
                ? "你保存的 Key 会驱动每一次分析。"
                : "Your saved key powers every analysis."}
            </p>
          </div>
        </div>
        <Button type="button" variant="outline" onClick={() => void signOut()}>
          <LogOut className="h-4 w-4" />
          {isZh ? "退出登录" : "Sign out"}
        </Button>
      </div>
    );
  }

  return (
    <Card className="border-slate-800 bg-slate-950/80 shadow-none">
      <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Badge className="bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/10">
              Google
            </Badge>
            <span className="inline-flex items-center gap-1 text-xs uppercase tracking-widest text-slate-500">
              <KeyRound className="h-3.5 w-3.5" />
              {isZh ? "使用自己的 Key" : "Bring your own key"}
            </span>
          </div>
          <p className="text-sm font-medium text-slate-100">
            {isZh ? "接入你的账号" : "Connect your account"}
          </p>
          <p className="max-w-xl text-sm text-slate-400">
            {isZh
              ? "免费试用用完后，用 Google 登录并继续使用你自己的 Key。"
              : "Sign in with Google after your free trial and continue with your own key."}
          </p>
        </div>
        <Button type="button" onClick={() => void signIn("google")}>
          <LogIn className="h-4 w-4" />
          {isZh ? "使用 Google 登录" : "Continue with Google"}
        </Button>
      </CardContent>
    </Card>
  );
}
