import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LandingPage from "@/app/page";

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
          name: /把.*财报阅读.*变成一块真正可用的研究界面/,
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
          name: /Turn.*earnings reading.*into a research interface you can actually use/,
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
        screen.getByText("Not a one-line answer, but a full page of research context"),
      ).toBeInTheDocument();
    });
  });
});
