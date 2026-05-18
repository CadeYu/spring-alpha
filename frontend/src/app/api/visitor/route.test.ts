import { describe, expect, it } from "vitest";
import { GET } from "./route";

describe("visitor id route", () => {
  it("returns a visitor id cookie when none is present", async () => {
    const response = await GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("spring-alpha-visitor-id=");
  });
});
