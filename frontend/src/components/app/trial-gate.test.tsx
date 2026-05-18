import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TrialGate } from "@/components/app/trial-gate";

describe("TrialGate", () => {
  it("shows the landing trial wall copy when trial is exhausted", () => {
    render(<TrialGate status="trial_exhausted" />);

    expect(
      screen.getByText("You have used your free analysis."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /sign in with google/i }),
    ).toBeInTheDocument();
  });

  it("renders nothing for active anonymous access", () => {
    const { container } = render(<TrialGate status="anonymous_ready" />);
    expect(container).toBeEmptyDOMElement();
  });
});
