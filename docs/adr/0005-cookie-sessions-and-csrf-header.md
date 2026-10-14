# Server-side sessions in a cookie, with a required request header

Signing in starts a session stored in Postgres; the browser holds a random token in an HTTP-only, SameSite=Lax cookie, and the database holds only the token's hash. We chose this over JWTs because signing out, and removing a banned user, must take effect immediately, which a self-contained token cannot do without a revocation list anyway. Because a cookie is sent automatically, every state-changing request must also carry an `X-Horatio` header. Browsers will not add a custom header to a cross-site request without CORS permission, and this API grants none, so the header blocks cross-site request forgery without per-form tokens.

## Consequences

- The frontend must send `X-Horatio` on every POST, PUT, PATCH and DELETE.
- The API and frontend are served from the same site. Splitting them across sites would need CORS and a different CSRF defence.
- Passwords are argon2. Bcrypt hashes imported from Yorick still verify and are replaced with argon2 at the user's next sign-in, so players keep their passwords.
