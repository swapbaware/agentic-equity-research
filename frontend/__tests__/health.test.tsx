import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HealthPage from "@/app/health/page";

describe("HealthPage", () => {
  it("renders the system health heading", () => {
    render(<HealthPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "System Health",
    );
  });

  it("shows frontend status as running", () => {
    render(<HealthPage />);
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  it("mentions the backend health endpoint", () => {
    render(<HealthPage />);
    expect(screen.getByText("/health")).toBeInTheDocument();
  });
});
