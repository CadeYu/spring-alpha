import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TrialGate } from "@/components/app/trial-gate";

describe("TrialGate", () => {
  it("shows the landing trial wall copy when trial is exhausted", () => {
    render(<TrialGate status="trial_exhausted" />);

    expect(
      screen.getByText("You have used all 3 free analyses."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /sign in with google/i }),
    ).toBeInTheDocument();
  });

  it("renders Chinese copy when trial is exhausted in zh locale", () => {
    render(<TrialGate status="trial_exhausted" lang="zh" />);

    expect(screen.getByText("你已经用完 3 次免费分析。")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /使用 google 登录/i }),
    ).toBeInTheDocument();
  });

  it("renders nothing for active anonymous access", () => {
    const { container } = render(<TrialGate status="anonymous_ready" />);
    expect(container).toBeEmptyDOMElement();
  });
});
