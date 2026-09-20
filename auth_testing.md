# Emergent Managed Google Auth Testing Playbook

## Backend session test

Create a temporary user and session in the configured database, then call:

```bash
curl -X GET "$REACT_APP_BACKEND_URL/api/auth/me" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

Verify that the response contains the custom `user_id` and no MongoDB `_id`.

## Browser test

Verify that:

1. The login screen shows the Google sign-in button.
2. Clicking it redirects to `auth.emergentagent.com` with a dynamically derived app URL.
3. A returned `#session_id=...` is processed before protected-route checks.
4. The backend exchanges the session ID and sets an HTTP-only `session_token` cookie.
5. The app redirects to the dashboard and `/api/auth/me` returns the user.
6. Logout clears the session and returns the user to login.

## Security checks

- Do not hardcode or provide fallback redirect URLs.
- Keep the session token in an HTTP-only, secure, SameSite=None cookie.
- Validate sessions server-side through `/api/auth/me`.
- Never expose MongoDB `_id` in API responses.
- Google OAuth test identities do not use app-managed passwords.