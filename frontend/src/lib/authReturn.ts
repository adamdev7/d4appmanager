const RETURN_KEY = "auth_return_to";

/** Remember where a signed-out visitor was headed, so login can send them back. */
export function rememberAuthReturn(path: string) {
  if (!path.startsWith("/") || path.startsWith("//")) return;
  if (
    path.startsWith("/login") ||
    path.startsWith("/register") ||
    path.startsWith("/forgot-password") ||
    path.startsWith("/verify-email") ||
    path.startsWith("/auth/")
  ) {
    return;
  }
  sessionStorage.setItem(RETURN_KEY, path);
}

/** Read and clear the saved return path. Falls back to the dashboard. */
export function consumeAuthReturn(): string {
  const path = sessionStorage.getItem(RETURN_KEY);
  sessionStorage.removeItem(RETURN_KEY);
  if (path && path.startsWith("/") && !path.startsWith("//")) return path;
  return "/dashboard";
}
