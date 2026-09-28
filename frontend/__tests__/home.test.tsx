import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "@/app/page";

describe("HomePage", () => {
  it("renders the application title", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Agentic Equity Research",
    );
  });

  it("shows the current phase", () => {
    render(<HomePage />);
    expect(screen.getByText(/Phase 2/)).toBeInTheDocument();
  });
});
