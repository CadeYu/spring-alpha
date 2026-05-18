import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthBanner } from "@/components/app/auth-banner";

let sessionState: {
  data: null | {
    user?: {
      email?: string | null;
      name?: string | null;
      image?: string | null;
    } | null;
  };
  status: "authenticated" | "unauthenticated" | "loading";
};

const signInMock = vi.fn();
const signOutMock = vi.fn();

vi.mock("next-auth/react", () => ({
  useSession: () => sessionState,
  signIn: (...args: unknown[]) => signInMock(...args),
  signOut: (...args: unknown[]) => signOutMock(...args),
}));

describe("AuthBanner", () => {
  beforeEach(() => {
    sessionState = { data: null, status: "unauthenticated" };
    signInMock.mockClear();
    signOutMock.mockClear();
  });

  it("prompts Google sign in when unauthenticated", () => {
    render(<AuthBanner />);

    expect(screen.getByText("Bring your own key")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /continue with google/i }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /continue with google/i }),
    );
    expect(signInMock).toHaveBeenCalledWith("google");
  });

  it("shows the current user and sign out action when authenticated", () => {
    sessionState = {
      data: { user: { email: "cadeyu@example.com", name: "Cade" } },
      status: "authenticated",
    };

    render(<AuthBanner />);

    expect(screen.getByText("cadeyu@example.com")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));
    expect(signOutMock).toHaveBeenCalled();
  });
});
