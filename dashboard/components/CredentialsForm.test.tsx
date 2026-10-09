import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CredentialsForm } from "./CredentialsForm";
import { loadCredentials, STORAGE_KEY } from "@/lib/credentials";

const SHA256_ABC =
  "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CredentialsForm", () => {
  it("renders labelled owner and password inputs", () => {
    render(<CredentialsForm onSaved={() => {}} />);
    expect(screen.getByLabelText(/owner/i)).toBeInTheDocument();
    const key = screen.getByLabelText(/api key/i) as HTMLInputElement;
    expect(key.type).toBe("password");
  });

  it("hashes and saves on submit, calls onSaved, and clears the key field", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    render(<CredentialsForm onSaved={onSaved} />);

    await user.type(screen.getByLabelText(/owner/i), "alice");
    const key = screen.getByLabelText(/api key/i) as HTMLInputElement;
    await user.type(key, "abc");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(loadCredentials()).toEqual({ ownerId: "alice", keyHash: SHA256_ABC });
    expect(localStorage.getItem(STORAGE_KEY)).not.toContain("abc");
    expect(key.value).toBe("");
  });

  it("renders an error message in an alert region", () => {
    render(<CredentialsForm onSaved={() => {}} error="Credentials not accepted" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Credentials not accepted");
  });
});
