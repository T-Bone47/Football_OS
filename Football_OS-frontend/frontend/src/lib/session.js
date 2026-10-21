import { createContext, useContext } from "react";

// The authenticated profile is resolved once by ProtectedRoute. The shell and its
// user menu read it from here instead of issuing a second /auth/me request.
export const SessionContext = createContext(null);

export function useSession() {
  return useContext(SessionContext);
}
