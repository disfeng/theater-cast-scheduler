import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import App from "../src/App";

test("renders login screen by default", () => {
  render(<App />);
  expect(screen.getByText("剧场卡司排班")).toBeInTheDocument();
  expect(screen.getByLabelText("邮箱")).toBeInTheDocument();
});
