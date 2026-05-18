import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LandingPage from "@/app/page";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

vi.mock("next/image", () => ({
  default: ({
    priority,
    fill,
    ...props
  }: React.ImgHTMLAttributes<HTMLImageElement> & {
    priority?: boolean;
    fill?: boolean;
  }) => (
    <>
      {void priority}
      {void fill}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img {...props} alt={props.alt ?? ""} />
    </>
  ),
}));

describe("Landing page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
    pushMock.mockClear();
  });

  it("renders Chinese copy by default for zh browsers", async () => {
    vi.stubGlobal("navigator", {
      ...window.navigator,
      language: "zh-CN",
    });

    render(<LandingPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", {
          name: /更快读懂每一次财报/,
        }),
      ).toBeInTheDocument();
    });
  });

  it("switches to English and persists the locale", async () => {
    vi.stubGlobal("navigator", {
      ...window.navigator,
      language: "zh-CN",
    });

    render(<LandingPage />);

    fireEvent.click(screen.getByRole("button", { name: "语言: EN" }));

    await waitFor(() => {
      expect(
        screen.getByRole("heading", {
          name: /Research faster at Any earnings call/,
        }),
      ).toBeInTheDocument();
    });

    expect(window.localStorage.getItem("spring-alpha-landing-locale")).toBe(
      "en",
    );
  });

  it("uses the saved locale on reload", async () => {
    window.localStorage.setItem("spring-alpha-landing-locale", "en");
    vi.stubGlobal("navigator", {
      ...window.navigator,
      language: "zh-CN",
    });

    render(<LandingPage />);

    await waitFor(() => {
      expect(
        screen.getByText("One ticker. Three agents. One research surface."),
      ).toBeInTheDocument();
    });
  });

  it("renders a ticker search entry on the landing page", () => {
    render(<LandingPage />);

    expect(
      screen.getByLabelText(/enter ticker|输入股票代码/i),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("输入股票代码 (如 AAPL, MSFT)"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /analyze ticker|开始分析/i }),
    ).toBeInTheDocument();
  });

  it("uses the same English ticker placeholder as the app", async () => {
    window.localStorage.setItem("spring-alpha-landing-locale", "en");

    render(<LandingPage />);

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText("Enter Ticker (e.g., AAPL, MSFT, TSLA)"),
      ).toBeInTheDocument();
    });
  });

  it("routes the landing ticker search into the app", () => {
    render(<LandingPage />);

    fireEvent.change(screen.getByLabelText(/enter ticker|输入股票代码/i), {
      target: { value: "AAPL" },
    });
    fireEvent.click(screen.getByRole("button", { name: /analyze ticker|开始分析/i }));

    expect(pushMock).toHaveBeenCalledWith("/app?ticker=AAPL");
  });
});
